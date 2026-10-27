"""Search-key folding and BRL money helpers (design §5.2)."""

import unicodedata
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# Treated as word separators, so "GN-15" and "gn 15" fold alike.
_SEPARATORS = str.maketrans({"-": " ", "/": " "})


def fold(text: str) -> str:
    """Return the accent- and case-insensitive search key for `text`.

    NFKD, combining marks stripped, casefolded, `-` and `/` read as spaces,
    whitespace collapsed. Only used for matching; display text is never folded.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().translate(_SEPARATORS).split())


def round_money(value: Decimal | int | float) -> Decimal:
    """Round to 2 places with ROUND_HALF_UP.

    A float goes through `str()` first, so 0.125 rounds to 0.13 as written.
    """
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def format_brl(value: Decimal | int | float) -> str:
    """Format as Brazilian reais, e.g. `R$ 2.199,00`."""
    us_style = f"{round_money(value):,.2f}"
    return "R$ " + us_style.translate(str.maketrans({",": ".", ".": ","}))
