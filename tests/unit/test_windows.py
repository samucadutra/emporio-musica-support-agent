"""Return and warranty windows (design §6.4, FR-07)."""

from datetime import date

import pytest

from emporio_musica_support_agent.data.models import Order
from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.domain.windows import (
    EXCLUSIONS_TO_CHECK,
    NOTE_CANCELLED,
    NOTE_FUTURE_ORDER,
    NOTE_NO_RECEIPT_DATE,
    NOTE_NOT_DELIVERED,
    WINDOW_RULES,
    ReturnWindows,
    Window,
    compute_windows,
    is_late,
)

ALL_WINDOWS = [
    "direito_de_arrependimento",
    "troca_por_defeito",
    "troca_por_preferencia",
    "garantia_legal",
]


def order(repo: Repository, order_id: int) -> Order:
    found = repo.get_order(order_id)
    assert found is not None
    return found


def windows_at(repo: Repository, order_id: int, reference: date) -> ReturnWindows:
    check = compute_windows(order(repo, order_id), reference)
    assert check.note is None
    assert check.windows is not None
    return check.windows


def window(windows: ReturnWindows, name: str) -> Window:
    return next(w for w in windows.windows if w.name == name)


def test_order_7_inside_withdrawal_window(repo: Repository) -> None:
    windows = windows_at(repo, 7, date(2026, 2, 20))
    withdrawal = window(windows, "direito_de_arrependimento")

    assert windows.receipt_date_assumed == date(2026, 2, 17)
    assert [w.name for w in windows.windows] == [rule[0] for rule in WINDOW_RULES]
    assert (withdrawal.open, withdrawal.days_elapsed) == (True, 3)
    assert withdrawal.deadline == date(2026, 2, 24)
    assert windows.open_now == ALL_WINDOWS


def test_order_7_only_legal_warranty_left(repo: Repository) -> None:
    windows = windows_at(repo, 7, date(2026, 3, 23))
    legal = window(windows, "garantia_legal")

    assert window(windows, "direito_de_arrependimento").days_elapsed == 34
    assert window(windows, "troca_por_defeito").days_elapsed == 48
    assert not window(windows, "troca_por_preferencia").open
    assert (legal.open, legal.deadline) == (True, date(2026, 5, 18))
    assert windows.open_now == ["garantia_legal"]


@pytest.mark.parametrize(
    ("name", "reference", "is_open"),
    [
        ("direito_de_arrependimento", date(2026, 2, 24), True),  # day 7
        ("direito_de_arrependimento", date(2026, 2, 25), False),  # day 8
        ("troca_por_defeito", date(2026, 3, 5), True),  # 30 days after purchase
        ("troca_por_defeito", date(2026, 3, 6), False),
        ("garantia_legal", date(2026, 5, 18), True),  # day 90
        ("garantia_legal", date(2026, 5, 19), False),
    ],
)
def test_last_day_is_still_open(
    repo: Repository, name: str, reference: date, is_open: bool
) -> None:
    assert window(windows_at(repo, 7, reference), name).open is is_open


def test_defect_exchange_counts_from_purchase(repo: Repository) -> None:
    defect = window(windows_at(repo, 7, date(2026, 2, 20)), "troca_por_defeito")

    assert (defect.starts_from, defect.start_date) == ("compra", date(2026, 2, 3))


@pytest.mark.parametrize(
    ("order_id", "reference", "note"),
    [
        (8, date(2026, 3, 23), NOTE_NOT_DELIVERED),  # shipped
        (13, date(2026, 3, 23), NOTE_NOT_DELIVERED),  # pending
        (17, date(2026, 3, 23), NOTE_CANCELLED),
        (7, date(2026, 2, 1), NOTE_FUTURE_ORDER),  # before the order date
    ],
)
def test_no_windows(repo: Repository, order_id: int, reference: date, note: str) -> None:
    check = compute_windows(order(repo, order_id), reference)

    assert check.windows is None
    assert check.note == note


def test_delivered_without_receipt_date(repo: Repository) -> None:
    no_receipt = order(repo, 7).model_copy(update={"estimated_delivery": None})

    assert compute_windows(no_receipt, date(2026, 3, 23)).note == NOTE_NO_RECEIPT_DATE


def test_fixed_notes(repo: Repository) -> None:
    windows = windows_at(repo, 7, date(2026, 3, 23))

    assert windows.exclusions_to_check == list(EXCLUSIONS_TO_CHECK)
    assert len(windows.exclusions_to_check) == 3
    assert "§8.2" in windows.manufacturer_warranty_note


def test_is_late(repo: Repository) -> None:
    shipped = order(repo, 8)

    assert is_late(shipped, date(2026, 3, 23))
    assert not is_late(shipped, date(2026, 2, 28))  # due today, not late yet
    assert not is_late(order(repo, 7), date(2026, 3, 23))  # delivered
    no_estimate = shipped.model_copy(update={"estimated_delivery": None})
    assert not is_late(no_estimate, date(2026, 3, 23))
