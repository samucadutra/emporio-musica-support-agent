"""Contact matching and PII masking."""

import csv
from pathlib import Path

import pytest

from emporio_musica_support_agent.privacy import (
    emails_match,
    mask_email,
    mask_phone,
    mask_pii,
    phones_match,
)

CUSTOMERS_CSV = Path(__file__).parents[2] / "data" / "desafio_tecnico_ai_eng - customers.csv"

# Customer 14, who placed order 7.
STORED_EMAIL = "leticia.rocha@jmail.com"
STORED_PHONE = "(67) 99789-0123"


@pytest.mark.parametrize(
    "given", ["67997890123", "+55 (67) 99789-0123", "067 99789-0123", "5567997890123"]
)
def test_phone_variants_match(given: str) -> None:
    assert phones_match(given, STORED_PHONE)


@pytest.mark.parametrize("given", ["99789-0123", "(67) 99789-0124", ""])
def test_phone_mismatches(given: str) -> None:
    assert not phones_match(given, STORED_PHONE)


@pytest.mark.parametrize("given", [" Leticia.Rocha@JMAIL.com ", "leticia.rocha @jmail.com"])
def test_email_variants_match(given: str) -> None:
    assert emails_match(given, STORED_EMAIL)


@pytest.mark.parametrize("given", ["leticia.rocha@coldmail.com", ""])
def test_email_mismatches(given: str) -> None:
    assert not emails_match(given, STORED_EMAIL)


def test_blank_contacts_never_match() -> None:
    assert not emails_match("", "")
    assert not phones_match("", "")


def test_mask_email() -> None:
    assert mask_email("leticia.rocha@jmail.com") == "le***@jmail.com"
    assert mask_email("ab@x.com") == "a***@x.com"
    assert mask_email("not-an-email") == "***"


def test_mask_phone_keeps_only_last_digits() -> None:
    assert mask_phone("(67) 99789-0123") == "***-0123"


@pytest.mark.parametrize(
    "contact",
    ["(67) 3341-4444", "(67) 3321-4500", "+55 67 3341-4444", "contato@emporiodamusica.com.br"],
)
def test_store_contacts_are_not_masked(contact: str) -> None:
    text = f"Fale com a loja: {contact}."

    assert mask_pii(text) == text


def test_mask_pii_in_mixed_text() -> None:
    text = (
        "Sou a Letícia, email leticia.rocha@jmail.com, tel (67) 99789-0123 ou 99789-0123. "
        "Pedido 7 de 2026-03-23, CEP 79202-333, rastreio BRAB1234567BR, "
        "valor R$ 2.199,00, protocolo EMP-20260323-7F3A."
    )

    masked = mask_pii(text)

    assert masked == (
        "Sou a Letícia, email le***@jmail.com, tel ***-0123 ou ***-0123. "
        "Pedido 7 de 2026-03-23, CEP 79202-333, rastreio BRAB1234567BR, "
        "valor R$ 2.199,00, protocolo EMP-20260323-7F3A."
    )


def test_mask_pii_leaves_text_without_pii_unchanged() -> None:
    text = "Quero um violão até R$ 1.000,00 para o dia 2026-03-23."

    assert mask_pii(text) == text


def test_every_customer_contact_is_masked() -> None:
    with CUSTOMERS_CSV.open(encoding="utf-8", newline="") as f:
        customers = list(csv.DictReader(f))

    assert len(customers) == 50
    for customer in customers:
        masked = mask_pii(f"email {customer['email']} telefone {customer['phone']}")
        assert customer["email"] not in masked
        assert customer["phone"] not in masked
