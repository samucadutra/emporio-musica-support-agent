"""Policy PDF extraction and the facts coded from it (design §7, A-06, A-21)."""

import re
from decimal import Decimal
from pathlib import Path

import pytest

from emporio_musica_support_agent.data.loader import policy_path
from emporio_musica_support_agent.domain import store
from emporio_musica_support_agent.domain.pricing import (
    INSTALLMENT_TIERS,
    MAX_INSTALLMENTS,
    PIX_DISCOUNT_PERCENT,
)
from emporio_musica_support_agent.domain.windows import WINDOW_RULES
from emporio_musica_support_agent.rag.extract import (
    EMAIL_FIX,
    EMAIL_TYPO,
    FOOTER_RE,
    HEADER_RE,
    TRAILER_LINES,
    PolicyText,
    clean_line,
    extract_policy,
)
from emporio_musica_support_agent.text import format_brl


@pytest.fixture(scope="session")
def policy(data_dir: Path) -> PolicyText:
    return extract_policy(policy_path(data_dir))


@pytest.fixture(scope="session")
def flat(policy: PolicyText) -> str:
    """Whitespace-flattened text: numbers like "90\\n(noventa)" wrap across lines."""
    return " ".join(policy.text.split())


def test_headers_footers_and_trailer_removed(policy: PolicyText) -> None:
    lines = policy.text.splitlines()

    assert not any(FOOTER_RE.match(line) or HEADER_RE.match(line.strip()) for line in lines)
    assert not any(trailer in policy.text for trailer in TRAILER_LINES)


def test_cover_kept(policy: PolicyText) -> None:
    assert "MANUAL DE POLÍTICAS E PROCEDIMENTOS" in policy.text
    assert "Versão 2.1 — Junho de 2025" in policy.text


def test_email_typo_fixed(policy: PolicyText) -> None:
    assert EMAIL_TYPO not in policy.text
    assert policy.text.count(EMAIL_FIX) >= 2  # cover and §1.2


@pytest.mark.parametrize("fact", [store.ADDRESS, store.PHONE, store.WHATSAPP, store.EMAIL])
def test_store_contacts_in_policy(policy: PolicyText, fact: str) -> None:
    assert fact in policy.text


@pytest.mark.parametrize(("days", "hours"), store.HOURS_TABLE)
def test_opening_hours_rows_readable(policy: PolicyText, days: str, hours: str) -> None:
    assert f"{days} | {hours}" in policy.text


@pytest.mark.parametrize("length", sorted({rule[3] for rule in WINDOW_RULES}))
def test_window_lengths_in_policy(flat: str, length: int) -> None:
    assert re.search(rf"\b{length}\b(?: \(\w+\))? dias", flat)


@pytest.mark.parametrize("minimum", [minimum for _, minimum in INSTALLMENT_TIERS])
def test_installment_minimums_in_policy(flat: str, minimum: Decimal) -> None:
    assert format_brl(minimum) in flat


def test_payment_numbers_in_policy(flat: str) -> None:
    assert f"{MAX_INSTALLMENTS}x" in flat
    assert f"{PIX_DISCOUNT_PERCENT}% de desconto" in flat


@pytest.mark.parametrize("amount", ["R$ 500,00", "R$ 35,00"])
def test_metro_shipping_numbers_in_policy(flat: str, amount: str) -> None:
    assert amount in flat


def test_bullets_and_numbered_steps(policy: PolicyText) -> None:
    lines = policy.text.splitlines()

    assert "•" not in policy.text
    assert "    - Frete grátis para pedidos acima de R$ 500,00." in lines
    assert any(line.startswith("    1. Saudação:") for line in lines)
    assert not any(line.startswith("1. Saudação") for line in lines)
    assert "1. |" not in policy.text


@pytest.mark.parametrize(
    "heading",
    ["4.1 Direito de Arrependimento (Compras Online)", "5.2 Entregas para Outras Cidades"],
)
def test_headings_on_their_own_line_at_column_0(policy: PolicyText, heading: str) -> None:
    assert heading in policy.text.splitlines()


def test_whitespace_is_tidy(policy: PolicyText) -> None:
    assert "\n\n\n" not in policy.text
    assert not any(line != line.rstrip() for line in policy.text.splitlines())


def test_page_offsets(policy: PolicyText) -> None:
    starts = policy.page_starts

    assert len(starts) == 8
    assert starts[0] == 0
    assert list(starts) == sorted(set(starts))
    assert policy.page_at(0) == 1
    assert policy.page_at(policy.text.index("4.1 Direito")) == 4
    assert policy.page_at(policy.text.index("5.3 Código de Rastreamento")) == 5
    assert policy.page_at(len(policy.text) - 1) == 8


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        (
            " PIX              Pagamento à vista            5% de desconto",
            "PIX | Pagamento à vista | 5% de desconto",
        ),
        ("    •    Texto do item.", "    - Texto do item."),
        ("    2.   Entendimento: identificar.", "    2. Entendimento: identificar."),
        ("4.1 Direito de Arrependimento   ", "4.1 Direito de Arrependimento"),
        ("         continuação de linha", "         continuação de linha"),
    ],
)
def test_clean_line(raw: str, cleaned: str) -> None:
    assert clean_line(raw) == cleaned
