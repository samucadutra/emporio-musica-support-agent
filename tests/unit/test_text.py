"""Search-key folding, money rounding and BRL formatting."""

from decimal import Decimal

import pytest

from emporio_musica_support_agent.text import fold, format_brl, round_money


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("VIOLÃO", "violao"),
        ("Cedr-Natural", "cedr natural"),
        ("GN-15", "gn 15"),
        ("  Takamine   GD20 ", "takamine gd20"),
        ("Baterias/Percussão", "baterias percussao"),
        ("Teclados e Pianos", "teclados e pianos"),
        ("Ç", "c"),
    ],
)
def test_fold(raw: str, folded: str) -> None:
    assert fold(raw) == folded


def test_fold_is_accent_and_case_insensitive() -> None:
    assert fold("Violão") == fold("violao") == fold("VIOLAO")


def test_folded_query_matches_real_product_name() -> None:
    assert fold("Cedr-Natural") in fold("Giannini GN-15 Nylon Cedr Natural")


@pytest.mark.parametrize(
    ("value", "formatted"),
    [
        (0, "R$ 0,00"),
        (159.9, "R$ 159,90"),
        (Decimal("2089.05"), "R$ 2.089,05"),
        (19567, "R$ 19.567,00"),
        (Decimal("2199"), "R$ 2.199,00"),
        (Decimal("1234567.8"), "R$ 1.234.567,80"),
    ],
)
def test_format_brl(value: Decimal | int | float, formatted: str) -> None:
    assert format_brl(value) == formatted


@pytest.mark.parametrize(
    ("value", "rounded"),
    [
        (Decimal("0.125"), Decimal("0.13")),  # banker's rounding would give 0.12
        (Decimal("2.345"), Decimal("2.35")),
        (Decimal("2.344"), Decimal("2.34")),
        (Decimal("2199") * Decimal("0.95"), Decimal("2089.05")),
        (0.125, Decimal("0.13")),
    ],
)
def test_round_money_half_up(value: Decimal | float, rounded: Decimal) -> None:
    result = round_money(value)

    assert result == rounded
    assert result.as_tuple().exponent == -2
