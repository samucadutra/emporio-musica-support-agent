"""Order tool: get_order_status with customer verification (design §6.4)."""

from datetime import date
from zoneinfo import ZoneInfo

from emporio_musica_support_agent.clock import Clock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.models import OrderStatus
from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.domain.windows import compute_windows, is_late
from emporio_musica_support_agent.privacy import emails_match, phones_match
from emporio_musica_support_agent.tools.schemas import (
    Money,
    OrderItemOut,
    OrderStatusInput,
    OrderStatusResult,
    VerifiedOrder,
)

STATUS_LABELS: dict[OrderStatus, str] = {
    "pending": "pendente",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}
# Returned for an unknown order and for a contact mismatch alike, so the
# result never reveals which of the two was wrong.
NOT_VERIFIED = OrderStatusResult(verified=False, message="not_found_or_not_verified")


def reference_date(settings: Settings, clock: Clock) -> date:
    """The date for order rules: STORE_TODAY if set, else the store's local date (A-02)."""
    return settings.store_today or clock.now(ZoneInfo(settings.store_timezone)).date()


def get_order_status(
    repo: Repository, clock: Clock, settings: Settings, params: OrderStatusInput
) -> OrderStatusResult:
    """Look up one order after verifying the customer. Call ONLY when you have both the order
    number and the email or phone the customer used for the purchase. If either is missing, ask
    the customer first and don't call this tool with guessed values. If `verified` is false, say
    you couldn't find an order with those details and ask the customer to check them. Don't say
    whether the number or the contact was wrong. When verified, report status, items, total,
    payment, and the tracking code and estimated delivery if present. If `is_late` is true, say
    the delivery is late and offer to pass the case to the team. For returns, exchanges or
    warranty, decide ONLY from `windows` (`open`, `deadline`, `open_now`) and never compute dates
    yourself. Also call `search_policies` for the conditions. Never repeat the customer's email or
    phone.
    """
    order = repo.get_order(params.order_id)
    customer = repo.get_customer(order.customer_id) if order else None
    if order is None or customer is None:
        return NOT_VERIFIED.model_copy()
    # Every contact given must match; both when both are given.
    if params.email is not None and not emails_match(params.email, customer.email):
        return NOT_VERIFIED.model_copy()
    if params.phone is not None and not phones_match(params.phone, customer.phone):
        return NOT_VERIFIED.model_copy()

    items = []
    for item in repo.get_order_items(order.order_id):
        product = repo.get_product(item.product_id)
        name = product.name if product else f"produto {item.product_id}"
        items.append(OrderItemOut(product_id=item.product_id, name=name, quantity=item.quantity))

    today = reference_date(settings, clock)
    check = compute_windows(order, today)
    return OrderStatusResult(
        verified=True,
        order=VerifiedOrder(
            order_id=order.order_id,
            # Only the first name leaves this function; never email, phone or city (NFR-02).
            customer_first_name=customer.name.split()[0],
            status=order.status,
            status_label=STATUS_LABELS[order.status],
            order_date=order.order_date,
            items=items,
            total=Money.from_decimal(order.total_brl),  # as charged, never recomputed (A-16)
            payment=order.payment.label,
            tracking_code=order.tracking_code,
            estimated_delivery=order.estimated_delivery,
            is_late=is_late(order, today),
            notes=order.notes,
            windows=check.windows,
            windows_note=check.note,
        ),
    )
