"""CSV loading and cleaning rules (design §5.1–5.2)."""

import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from emporio_musica_support_agent.data.cleaning import (
    empty_to_none,
    parse_payment_method,
    parse_specs,
)
from emporio_musica_support_agent.data.loader import (
    TABLE_FILES,
    DataFileNotFoundError,
    StoreData,
    load_store_data,
    policy_path,
)
from emporio_musica_support_agent.data.models import Order, Product


@pytest.fixture(scope="session")
def store(data_dir: Path) -> StoreData:
    return load_store_data(data_dir)


def product(store: StoreData, product_id: int) -> Product:
    return next(p for p in store.products if p.product_id == product_id)


def order(store: StoreData, order_id: int) -> Order:
    return next(o for o in store.orders if o.order_id == order_id)


def test_row_counts(store: StoreData) -> None:
    counts = [
        len(store.categories),
        len(store.products),
        len(store.promotions),
        len(store.orders),
        len(store.order_items),
        len(store.customers),
    ]

    assert counts == [9, 65, 25, 20, 22, 50]


def test_products_sorted_by_id(store: StoreData) -> None:
    ids = [p.product_id for p in store.products]

    assert ids == sorted(ids)
    assert ids[-2:] == [144, 145]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("credit_12x", ("credit", 12, "cartão de crédito em 12x")),
        ("credit_3x", ("credit", 3, "cartão de crédito em 3x")),
        ("pix", ("pix", 1, "PIX")),
        ("debit", ("debit", 1, "cartão de débito")),
        ("boleto", ("boleto", 1, "boleto bancário")),
    ],
)
def test_parse_payment_method(raw: str, expected: tuple[str, int, str]) -> None:
    assert parse_payment_method(raw) == expected


def test_unknown_payment_method_raises() -> None:
    with pytest.raises(ValueError, match="bitcoin"):
        parse_payment_method("bitcoin")


def test_order_with_tracking(store: StoreData) -> None:
    first = order(store, 1)

    assert first.tracking_code == "BRAB1234567BR"
    assert first.estimated_delivery == date(2025, 10, 25)
    assert first.order_date == date(2025, 10, 15)


def test_empty_order_columns_are_none(store: StoreData) -> None:
    pending = order(store, 13)

    assert pending.tracking_code is None
    assert pending.estimated_delivery is None
    assert pending.notes is None


def test_order_fields_as_stored(store: StoreData) -> None:
    assert order(store, 17).notes
    assert order(store, 3).payment.label == "cartão de crédito em 12x"
    assert order(store, 3).payment_method == "credit_12x"
    assert order(store, 7).total_brl == Decimal("159.9")


def test_specs_parsed_to_dict(store: StoreData) -> None:
    assert product(store, 81).specs["top"] == "Spruce"
    assert product(store, 81).price_brl == Decimal("599.9")


def test_specs_must_be_an_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_specs("[]")


@pytest.mark.parametrize(
    ("product_id", "label"),
    [
        (81, "disponível"),
        (96, "temporariamente indisponível"),
        (113, "fora de catálogo"),
        (130, "em breve"),
        (136, "fora de catálogo"),  # discontinued, even with stock left
    ],
)
def test_availability_label(store: StoreData, product_id: int, label: str) -> None:
    assert product(store, product_id).availability == label


@pytest.mark.parametrize(
    ("product_id", "reliable"), [(134, True), (135, False), (144, False), (145, True)]
)
def test_description_reliable(store: StoreData, product_id: int, reliable: bool) -> None:
    assert product(store, product_id).description_reliable is reliable


def test_promotion_is_active_is_bool(store: StoreData) -> None:
    active = [p for p in store.promotions if p.is_active is True]

    assert len(active) == 4
    assert all(isinstance(p.is_active, bool) for p in store.promotions)


def test_empty_to_none() -> None:
    assert empty_to_none("") is None
    assert empty_to_none("x") == "x"
    assert empty_to_none(0) == 0


def test_missing_data_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(DataFileNotFoundError) as excinfo:
        load_store_data(tmp_path)

    assert excinfo.value.table == "categories"
    assert excinfo.value.path == tmp_path / TABLE_FILES["categories"]


def test_missing_policy_raises(tmp_path: Path) -> None:
    with pytest.raises(DataFileNotFoundError) as excinfo:
        policy_path(tmp_path)

    assert excinfo.value.table == "policy"


def test_policy_found(data_dir: Path) -> None:
    assert policy_path(data_dir).is_file()


def test_only_mapped_files_are_read(data_dir: Path, tmp_path: Path) -> None:
    for name in TABLE_FILES.values():
        shutil.copy(data_dir / name, tmp_path / name)
        (tmp_path / f"{name}:Zone.Identifier").write_text("[ZoneTransfer]\nZoneId=3\n")
    (tmp_path / "junk.csv").write_text("not,a,table\n")

    store = load_store_data(tmp_path)

    assert len(store.products) == 65
    assert len(store.customers) == 50
