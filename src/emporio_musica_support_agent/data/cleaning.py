"""Value-level cleaning rules applied on load; `data/` is never edited (design §5.2)."""

import json
import re
from typing import Literal

Availability = Literal["disponível", "temporariamente indisponível", "fora de catálogo", "em breve"]
PaymentMethod = Literal["pix", "debit", "credit", "boleto"]

# Issue #4 / decision D4: products 135–144 have descriptions and specs that contradict their
# names (e.g. 135 "Music Man" is described as a Fender). Never quote them; name and price only.
UNRELIABLE_DESCRIPTION_IDS: frozenset[int] = frozenset(range(135, 145))

PAYMENT_LABELS: dict[PaymentMethod, str] = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "credit": "cartão de crédito em {n}x",
    "boleto": "boleto bancário",
}
_CREDIT_RE = re.compile(r"credit_(\d+)x")


def empty_to_none(value: object) -> object:
    """CSV cells are never null, only empty: treat `""` as missing."""
    return None if value == "" else value


def parse_specs(raw: str) -> dict[str, str | int]:
    specs = json.loads(raw)
    if not isinstance(specs, dict):
        raise ValueError(f"specs must be a JSON object, got {type(specs).__name__}")
    return specs


def parse_payment_method(raw: str) -> tuple[PaymentMethod, int, str]:
    """Split `credit_12x` into ("credit", 12, "cartão de crédito em 12x")."""
    if match := _CREDIT_RE.fullmatch(raw):
        installments = int(match.group(1))
        return "credit", installments, PAYMENT_LABELS["credit"].format(n=installments)
    if raw in ("pix", "debit", "boleto"):
        return raw, 1, PAYMENT_LABELS[raw]
    raise ValueError(f"unknown payment method: {raw!r}")


def availability_label(status: str, stock_quantity: int) -> Availability:
    if status == "discontinued":
        return "fora de catálogo"
    if status == "coming_soon":
        return "em breve"
    return "disponível" if stock_quantity > 0 else "temporariamente indisponível"
