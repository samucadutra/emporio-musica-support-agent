"""The recorded example conversations (PRD §12) keep their promised shape and facts."""

import re
from pathlib import Path

import pytest

from emporio_musica_support_agent.domain.store import EMAIL

EXAMPLES = Path(__file__).parents[2] / "examples"
FILES = [
    "01-violoes-ate-1000.md",
    "02-endereco-e-horario.md",
    "03-preco-promocao-multiturno.md",
    "04-devolucao-pedido-7.md",
    "05-fora-de-escopo.md",
]
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\b\d{2}9\d{4}[- ]?\d{4}\b|\b9\d{4}-\d{4}\b")


def read(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def tool_blocks(text: str) -> list[str]:
    return re.findall(r"<details>.*?</details>", text, flags=re.DOTALL)


@pytest.mark.parametrize("name", FILES)
def test_header_states_model_and_store_today(name: str) -> None:
    text = read(name)
    assert re.search(r"^- Model: \S+", text, flags=re.MULTILINE)
    assert re.search(r"^- STORE_TODAY: .+", text, flags=re.MULTILINE)
    assert "**Lia:**" in text


@pytest.mark.parametrize("name", FILES)
def test_tool_blocks_hold_no_raw_contact_data(name: str) -> None:
    for block in tool_blocks(read(name)):
        for email in EMAIL_RE.findall(block):
            assert email == EMAIL or "***" in email, email
        assert not PHONE_RE.search(block)


def test_example_1_lists_the_12_buyable_violoes() -> None:
    text = read("01-violoes-ate-1000.md")
    assert text.count("\n- ") - text.count("`search_products`") >= 12
    for name in ("Memphis AC-39", "RC-104", "Woodstock", "TW-7"):
        assert name in text
    assert "GF-3D" not in text and "SN-7C" not in text


def test_example_3_has_pix_and_promotion_prices() -> None:
    text = read("03-preco-promocao-multiturno.md")
    for fact in ("R$ 2.199,00", "R$ 2.089,05", "R$ 549,00", "R$ 439,20", "20%"):
        assert fact in text


def test_example_4_covers_both_reference_dates() -> None:
    text = read("04-devolucao-pedido-7.md")
    assert "STORE_TODAY: 2026-02-20" in text
    assert "STORE_TODAY: 2026-03-23" in text
    assert "garantia legal" in text.lower()
