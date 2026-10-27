"""Return and warranty windows for an order (design §6.4, FR-07).

The model never does date arithmetic: it reads `open`, `deadline` and `open_now`.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from emporio_musica_support_agent.data.models import Order

WindowName = Literal[
    "direito_de_arrependimento", "troca_por_defeito", "troca_por_preferencia", "garantia_legal"
]
StartsFrom = Literal["recebimento", "compra"]

# (name, policy section, counted from, length in days), in FR-07 order.
WINDOW_RULES: tuple[tuple[WindowName, str, StartsFrom, int], ...] = (
    ("direito_de_arrependimento", "4.1", "recebimento", 7),
    ("troca_por_defeito", "4.2", "compra", 30),
    # §4.3 gives no start date; counted from receipt like §4.1 (A-19).
    ("troca_por_preferencia", "4.3", "recebimento", 7),
    ("garantia_legal", "8.1", "recebimento", 90),
)
MANUFACTURER_WARRANTY_NOTE = (
    "after the legal warranty: manufacturer warranty (6 months to 2 years, "
    "per the product's certificate), terms in §8.2"
)
# §4.4 exclusions. Orders don't record customization or "venda final", so the agent
# mentions them as conditions to check and never claims an order is excluded (A-15).
EXCLUSIONS_TO_CHECK: tuple[str, ...] = (
    "customized or set-up instruments (§4.4)",
    "liquidation items sold with an explicit 'venda final' notice (§4.4)",
    "wind-instrument mouthpieces (boquilhas) (§4.4)",
)

NOTE_FUTURE_ORDER = "order date is after the reference date"
NOTE_CANCELLED = "order cancelled"
NOTE_NOT_DELIVERED = "not delivered yet: receipt-based windows have not started"
NOTE_NO_RECEIPT_DATE = "receipt date unknown"


class Window(BaseModel):
    name: WindowName
    policy_section: str  # "4.1", "4.2", "4.3", "8.1"
    starts_from: StartsFrom
    start_date: date
    length_days: int  # 7, 30, 7, 90
    deadline: date  # start_date + length_days
    days_elapsed: int
    open: bool  # 0 <= days_elapsed <= length_days


class ReturnWindows(BaseModel):
    reference_date: date
    receipt_date_assumed: date  # estimated_delivery (A-01)
    windows: list[Window]  # in FR-07 order
    open_now: list[WindowName]  # names of open windows, in that order
    manufacturer_warranty_note: str
    exclusions_to_check: list[str]


@dataclass(frozen=True)
class WindowCheck:
    windows: ReturnWindows | None
    note: str | None  # why windows is None


def compute_windows(order: Order, reference_date: date) -> WindowCheck:
    """Windows for a delivered order on `reference_date`, or a note saying why there are none."""
    # The data snapshot can predate the clock's "today", or the reverse (D1).
    if order.order_date > reference_date:
        return WindowCheck(None, NOTE_FUTURE_ORDER)
    if order.status == "cancelled":
        return WindowCheck(None, NOTE_CANCELLED)
    if order.status != "delivered":
        return WindowCheck(None, NOTE_NOT_DELIVERED)
    if order.estimated_delivery is None:
        return WindowCheck(None, NOTE_NO_RECEIPT_DATE)

    receipt = order.estimated_delivery  # no actual delivery date in the data (A-01)
    windows = []
    for name, section, starts_from, length in WINDOW_RULES:
        start = receipt if starts_from == "recebimento" else order.order_date
        elapsed = (reference_date - start).days
        windows.append(
            Window(
                name=name,
                policy_section=section,
                starts_from=starts_from,
                start_date=start,
                length_days=length,
                deadline=start + timedelta(days=length),
                days_elapsed=elapsed,
                # "em até 7 dias corridos": the last day is still open.
                open=0 <= elapsed <= length,
            )
        )
    return WindowCheck(
        ReturnWindows(
            reference_date=reference_date,
            receipt_date_assumed=receipt,
            windows=windows,
            open_now=[w.name for w in windows if w.open],
            manufacturer_warranty_note=MANUFACTURER_WARRANTY_NOTE,
            exclusions_to_check=list(EXCLUSIONS_TO_CHECK),
        ),
        None,
    )


def is_late(order: Order, reference_date: date) -> bool:
    """A shipped order whose estimated delivery date has passed."""
    return (
        order.status == "shipped"
        and order.estimated_delivery is not None
        and order.estimated_delivery < reference_date
    )
