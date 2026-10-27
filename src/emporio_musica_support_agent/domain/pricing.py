"""Promotion, PIX and installment rules (design §6.2, A-05, A-11)."""

from dataclasses import dataclass
from decimal import Decimal

from emporio_musica_support_agent.data.models import Promotion
from emporio_musica_support_agent.text import round_money

PIX_DISCOUNT_PERCENT = 5
MAX_INSTALLMENTS = 12
# Policy §3.1 / A-11: (largest n in tier, minimum installment value).
INSTALLMENT_TIERS: tuple[tuple[int, Decimal], ...] = (
    (3, Decimal(50)),
    (6, Decimal(80)),
    (12, Decimal(100)),
)


@dataclass(frozen=True)
class InstallmentOption:
    n: int
    value: Decimal  # final / n, rounded half-up
    minimum: Decimal  # tier minimum for n
    allowed: bool


def _discounted(price: Decimal, percent: int) -> Decimal:
    return round_money(price * (100 - percent) / 100)


def final_price(price: Decimal, promotion: Promotion | None) -> Decimal:
    """List price minus the current promotion, if any. Pass only a current promotion."""
    return _discounted(price, promotion.discount_percent if promotion else 0)


def pix_price(price: Decimal, promotion: Promotion | None) -> Decimal | None:
    """5% off the list price; None when a promotion is current (PIX never stacks, §6.2)."""
    return None if promotion else _discounted(price, PIX_DISCOUNT_PERCENT)


def installment_minimum(n: int) -> Decimal:
    if not 1 <= n <= MAX_INSTALLMENTS:
        raise ValueError(f"installments must be between 1 and {MAX_INSTALLMENTS}, got {n}")
    return next(minimum for largest, minimum in INSTALLMENT_TIERS if n <= largest)


def installment_options(final: Decimal) -> list[InstallmentOption]:
    """Options for 1..12 installments. 1x is always allowed (A-11)."""
    options = []
    for n in range(1, MAX_INSTALLMENTS + 1):
        minimum = installment_minimum(n)
        # Compare the exact quotient, not the rounded value shown to the customer.
        allowed = n == 1 or final / n >= minimum
        options.append(InstallmentOption(n, round_money(final / n), minimum, allowed))
    return options


def max_installments(final: Decimal) -> int:
    """Largest allowed n; allowed options are always 1..max, since final / n falls as n grows
    while the minimum only rises."""
    return max(option.n for option in installment_options(final) if option.allowed)
