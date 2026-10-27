"""Start-up checks that the data and the policy still match the code (design §5.5).

Every failure is collected, so one run shows everything that changed.
"""

import re
from collections import defaultdict
from typing import get_args

from emporio_musica_support_agent.data.cleaning import PaymentMethod
from emporio_musica_support_agent.data.loader import StoreData
from emporio_musica_support_agent.data.models import OrderStatus, ProductStatus
from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.domain import store
from emporio_musica_support_agent.domain.pricing import (
    INSTALLMENT_TIERS,
    MAX_INSTALLMENTS,
    PIX_DISCOUNT_PERCENT,
)
from emporio_musica_support_agent.domain.windows import WINDOW_RULES
from emporio_musica_support_agent.text import format_brl

# Policy amounts the agent relies on but no code computes with yet (metro shipping, A-12).
POLICY_LITERALS: tuple[str, ...] = ("R$ 500,00", "R$ 35,00")


class DataValidationError(Exception):
    def __init__(self, failures: list[str]) -> None:
        self.failures = failures
        lines = "\n".join(f"- {failure}" for failure in failures)
        super().__init__(f"data validation failed ({len(failures)} problems):\n{lines}")


def _foreign_keys(data: StoreData) -> list[str]:
    categories = {c.category_id for c in data.categories}
    products = {p.product_id for p in data.products}
    orders = {o.order_id for o in data.orders}
    customers = {c.customer_id for c in data.customers}
    failures = [
        f"products: category_id {p.category_id} (product {p.product_id}) not in categories"
        for p in data.products
        if p.category_id not in categories
    ]
    failures += [
        f"promotions: product_id {p.product_id} (promotion {p.promotion_id}) not in products"
        for p in data.promotions
        if p.product_id not in products
    ]
    failures += [
        f"orders: customer_id {o.customer_id} (order {o.order_id}) not in customers"
        for o in data.orders
        if o.customer_id not in customers
    ]
    for item in data.order_items:
        if item.order_id not in orders:
            failures.append(f"order_items: order_id {item.order_id} not in orders")
        if item.product_id not in products:
            failures.append(
                f"order_items: product_id {item.product_id} (order {item.order_id}) not in products"
            )
    return failures


def _current_promotions(repo: Repository) -> list[str]:
    """At most one current promotion per product (D2)."""
    current: dict[int, list[int]] = defaultdict(list)
    for promotion in repo.data.promotions:
        product = repo.get_product(promotion.product_id)
        if promotion.is_active and product and product.availability == "disponível":
            current[promotion.product_id].append(promotion.promotion_id)
    return [
        f"product {product_id}: {len(ids)} current promotions ({', '.join(map(str, ids))})"
        for product_id, ids in sorted(current.items())
        if len(ids) > 1
    ]


def _enums(data: StoreData) -> list[str]:
    """Pydantic enforces these on load; this guards rows built any other way."""
    failures = [
        f"products: unknown status {p.status!r} (product {p.product_id})"
        for p in data.products
        if p.status not in get_args(ProductStatus)
    ]
    for o in data.orders:
        if o.status not in get_args(OrderStatus):
            failures.append(f"orders: unknown status {o.status!r} (order {o.order_id})")
        if o.payment.method not in get_args(PaymentMethod):
            failures.append(
                f"orders: unknown payment method {o.payment.method!r} (order {o.order_id})"
            )
    return failures


def _store_facts(policy_text: str) -> list[str]:
    facts = {
        "address": store.ADDRESS,
        "phone": store.PHONE,
        "WhatsApp": store.WHATSAPP,
        "email": store.EMAIL,
    }
    failures = [
        f"policy: store {name} {value!r} not found"
        for name, value in facts.items()
        if value not in policy_text
    ]
    failures += [
        f"policy: opening hours row {days} | {hours!r} not found"
        for days, hours in store.HOURS_TABLE
        if f"{days} | {hours}" not in policy_text
    ]
    return failures


def _policy_numbers(policy_text: str) -> list[str]:
    """Numbers coded from policy v2.1 must still be in it (A-21)."""
    # Numbers can wrap across lines ("90\n(noventa) dias"), so compare flattened text.
    flat = " ".join(policy_text.split())
    failures = [
        f"policy: {length}-day window not found"
        for length in sorted({rule[3] for rule in WINDOW_RULES})
        if not re.search(rf"\b{length}\b(?: \(\w+\))? dias", flat)
    ]
    expected = [format_brl(minimum) for _, minimum in INSTALLMENT_TIERS]
    expected += [f"{MAX_INSTALLMENTS}x", f"{PIX_DISCOUNT_PERCENT}% de desconto"]
    expected += POLICY_LITERALS
    failures += [f"policy: {value!r} not found" for value in expected if value not in flat]
    return failures


def validate(repo: Repository, policy_text: str) -> None:
    """Raise DataValidationError listing every failed check; return quietly otherwise."""
    failures = (
        _foreign_keys(repo.data)
        + _current_promotions(repo)
        + _enums(repo.data)
        + _store_facts(policy_text)
        + _policy_numbers(policy_text)
    )
    if failures:
        raise DataValidationError(failures)
