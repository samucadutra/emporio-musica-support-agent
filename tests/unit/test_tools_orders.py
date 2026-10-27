"""get_order_status: verification, output and privacy (design §6.4)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from emporio_musica_support_agent.clock import FixedClock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.domain.windows import NOTE_CANCELLED, NOTE_NOT_DELIVERED
from emporio_musica_support_agent.privacy import normalize_phone
from emporio_musica_support_agent.tools.orders import get_order_status, reference_date
from emporio_musica_support_agent.tools.schemas import (
    OrderStatusInput,
    OrderStatusResult,
    VerifiedOrder,
)

STORE_TZ = ZoneInfo("America/Campo_Grande")
CLOCK = FixedClock(datetime(2026, 2, 20, 10, tzinfo=STORE_TZ))
LETICIA_EMAIL = "leticia.rocha@jmail.com"


def settings(store_today: date | None = None) -> Settings:
    return Settings(_env_file=None, store_today=store_today)


def lookup(
    repo: Repository, store_today: date | None = None, **kwargs: object
) -> OrderStatusResult:
    return get_order_status(repo, CLOCK, settings(store_today), OrderStatusInput(**kwargs))


def verified(repo: Repository, store_today: date | None = None, **kwargs: object) -> VerifiedOrder:
    result = lookup(repo, store_today, **kwargs)
    assert result.verified
    assert result.order is not None
    return result.order


def owner_email(repo: Repository, order_id: int) -> str:
    order = repo.get_order(order_id)
    assert order is not None
    owner = repo.get_customer(order.customer_id)
    assert owner is not None
    return owner.email


def test_verified_by_email(repo: Repository) -> None:
    order = verified(repo, order_id=7, email=LETICIA_EMAIL)

    assert order.customer_first_name == "Letícia"
    assert order.status_label == "entregue"
    assert [(i.product_id, i.name, i.quantity) for i in order.items] == [
        (119, "Shelby SU-21S Soprano Sunburst", 1)
    ]
    assert order.payment == "cartão de crédito em 3x"


@pytest.mark.parametrize("phone", ["67997890123", "+55 (67) 99789-0123"])
def test_verified_by_phone(repo: Repository, phone: str) -> None:
    assert verified(repo, order_id=7, phone=phone).order_id == 7


@pytest.mark.parametrize(
    "kwargs",
    [
        {"order_id": 7, "email": "leticia@jmail.com"},
        {"order_id": 7, "email": "lucas.mendes@jmail.com"},  # another real customer
        {"order_id": 7, "email": LETICIA_EMAIL, "phone": "67999999999"},
    ],
)
def test_mismatch_equals_unknown_order(repo: Repository, kwargs: dict[str, object]) -> None:
    unknown = lookup(repo, order_id=9999, email=LETICIA_EMAIL)
    mismatch = lookup(repo, **kwargs)

    assert mismatch.model_dump_json() == unknown.model_dump_json()
    assert (mismatch.verified, mismatch.order) == (False, None)
    assert mismatch.message == "not_found_or_not_verified"


def test_both_contacts_right(repo: Repository) -> None:
    assert verified(repo, order_id=7, email=LETICIA_EMAIL, phone="(67) 99789-0123")


def test_total_as_stored(repo: Repository) -> None:
    total = verified(repo, order_id=3, email=owner_email(repo, 3)).total

    assert (total.brl, total.fmt) == (3450.0, "R$ 3.450,00")  # item 130 lists at R$ 1.749


def test_cancelled_order(repo: Repository) -> None:
    order = verified(repo, order_id=17, email=owner_email(repo, 17))

    assert order.notes
    assert order.status_label == "cancelado"
    assert (order.windows, order.windows_note) == (None, NOTE_CANCELLED)


def test_late_shipment_with_store_today(repo: Repository) -> None:
    email = owner_email(repo, 8)

    late = verified(repo, date(2026, 3, 23), order_id=8, email=email)
    on_clock = verified(repo, None, order_id=8, email=email)  # clock says 2026-02-20

    assert late.is_late
    assert late.tracking_code == "BRJL5544332BR"
    assert late.windows_note == NOTE_NOT_DELIVERED
    assert not on_clock.is_late


def test_windows_follow_store_today(repo: Repository) -> None:
    inside = verified(repo, date(2026, 2, 20), order_id=7, email=LETICIA_EMAIL)
    outside = verified(repo, date(2026, 3, 23), order_id=7, email=LETICIA_EMAIL)

    assert inside.windows is not None
    assert "direito_de_arrependimento" in inside.windows.open_now
    assert outside.windows is not None
    assert outside.windows.open_now == ["garantia_legal"]


def test_reference_date() -> None:
    assert reference_date(settings(date(2026, 3, 23)), CLOCK) == date(2026, 3, 23)
    assert reference_date(settings(None), CLOCK) == date(2026, 2, 20)


def test_no_customer_data_in_any_verified_order(repo: Repository) -> None:
    customers = [c for c in (repo.get_customer(i) for i in range(1, 51)) if c is not None]
    for order_id in range(1, 21):
        order = repo.get_order(order_id)
        assert order is not None
        owner = repo.get_customer(order.customer_id)
        assert owner is not None

        payload = lookup(
            repo, date(2026, 3, 23), order_id=order_id, email=owner.email
        ).model_dump_json()

        assert '"verified":true' in payload
        assert "@" not in payload
        assert "customer_id" not in payload
        assert owner.city not in payload
        for customer in customers:
            assert customer.phone not in payload
            assert str(normalize_phone(customer.phone)) not in payload
            assert customer.name not in payload


@pytest.mark.parametrize("kwargs", [{"order_id": 7}, {"order_id": 7, "email": "  "}])
def test_contact_required(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="ask the customer for the email or phone"):
        OrderStatusInput(**kwargs)


def test_order_id_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        OrderStatusInput(order_id=0, email=LETICIA_EMAIL)
