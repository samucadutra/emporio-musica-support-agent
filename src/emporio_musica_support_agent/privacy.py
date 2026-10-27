"""Contact matching for order verification and PII masking (design §6.4, §6.7)."""

import re

# The store's own public contacts (A-06), never masked.
STORE_EMAIL = "contato@emporiodamusica.com.br"
STORE_PHONE_DIGITS: frozenset[str] = frozenset({"6733414444", "6733214500"})  # phone, WhatsApp

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Digit runs with phone punctuation; whether one is a phone is decided by its digit count.
_PHONE_CANDIDATE_RE = re.compile(r"(?<!\w)\+?\(?\d[\d\s().-]{6,}\d(?!\w)")
# 9 digits: mobile without area code; 13: +55, area code and mobile. Dates and ZIP codes have 8.
_PHONE_DIGIT_COUNTS = range(9, 14)


def _digits(text: str) -> str:
    return "".join(c for c in text if c.isdigit())


def normalize_email(email: str) -> str:
    """Strip, remove inner whitespace and casefold."""
    return "".join(email.split()).casefold()


def normalize_phone(phone: str) -> str | None:
    """Return the 11-digit area code + number, or None if `phone` isn't one.

    A leading country code `55` (13 digits) or trunk prefix `0` (12 digits) is dropped.
    """
    digits = _digits(phone)
    if len(digits) == 13 and digits.startswith("55"):
        digits = digits[2:]
    elif len(digits) == 12 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 11 else None


def emails_match(given: str, stored: str) -> bool:
    normalized = normalize_email(given)
    return bool(normalized) and normalized == normalize_email(stored)


def phones_match(given: str, stored: str) -> bool:
    normalized = normalize_phone(given)
    return normalized is not None and normalized == normalize_phone(stored)


def mask_email(email: str) -> str:
    """Keep the first two characters of the local part: `le***@jmail.com`."""
    local, at, domain = email.partition("@")
    if not at:
        return "***"
    keep = 2 if len(local) > 2 else 1
    return f"{local[:keep]}***@{domain}"


def mask_phone(phone: str) -> str:
    """Keep only the last four digits: `***-0123`."""
    digits = _digits(phone)
    return f"***-{digits[-4:]}" if len(digits) >= 4 else "***"


def _mask_email_match(match: re.Match[str]) -> str:
    email = match.group()
    return email if email.casefold() == STORE_EMAIL else mask_email(email)


def _mask_phone_match(match: re.Match[str]) -> str:
    candidate = match.group()
    digits = _digits(candidate)
    if len(digits) not in _PHONE_DIGIT_COUNTS or digits[-10:] in STORE_PHONE_DIGITS:
        return candidate
    return mask_phone(candidate)


def mask_pii(text: str) -> str:
    """Mask every email and phone number in `text`, except the store's own contacts."""
    return _PHONE_CANDIDATE_RE.sub(_mask_phone_match, _EMAIL_RE.sub(_mask_email_match, text))
