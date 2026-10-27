"""Clean policy text from the PDF (design §7, extraction).

Layout mode keeps lines and table columns; the default mode emits one word per
line. Leading indentation is kept, because headings start at column 0 and the
indented numbered steps in §7.2 must not look like headings (T17).
"""

import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

HEADER_RE = re.compile(r"^Empório da Música\s+Manual de Políticas e Procedimentos$")
FOOTER_RE = re.compile(r"^\s*Página \d+$")
TRAILER_LINES: tuple[str, ...] = (
    "Empório da Música — Sua música começa aqui.",
    "Última atualização: Junho de 2025 — Versão 2.1",
)
# D3: §1.2 spells the host with an accent, which isn't a valid plain-ASCII host.
EMAIL_TYPO = "contato@empóriodamusica.com.br"
EMAIL_FIX = "contato@emporiodamusica.com.br"

_INDENT_RE = re.compile(r"^( *)(.*)$")
_BULLET_RE = re.compile(r"^•\s*")
_NUMBERED_RE = re.compile(r"^(\d+\.)\s{2,}")
_COLUMN_GAP_RE = re.compile(r" {2,}")
_BLANK_RUN_RE = re.compile(r"\n{3,}")
PAGE_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class PolicyText:
    text: str
    page_starts: tuple[int, ...]  # offset in `text` where each page starts

    def page_at(self, offset: int) -> int:
        """1-based page number for a character offset."""
        return bisect_right(self.page_starts, offset)


def clean_line(line: str) -> str:
    """Bullets to "- ", tidy "N." markers, column gaps to " | "; keep indentation."""
    match = _INDENT_RE.match(line.rstrip())
    assert match is not None  # the pattern matches any line
    indent, body = match.groups()
    body = _BULLET_RE.sub("- ", body)
    body = _NUMBERED_RE.sub(r"\1 ", body)
    body = _COLUMN_GAP_RE.sub(" | ", body)
    # Table rows read better flush left: "Sábado | 09:00 às 13:00".
    if " | " in body:
        indent = ""
    return indent + body


def _is_noise(line: str) -> bool:
    stripped = line.strip()
    return bool(HEADER_RE.match(stripped) or FOOTER_RE.match(line)) or stripped in TRAILER_LINES


def clean_page(raw: str) -> str:
    """Drop header, footer and trailer lines, clean the rest, collapse blank lines."""
    lines = unicodedata.normalize("NFC", raw).splitlines()
    kept = [clean_line(line) for line in lines if not _is_noise(line)]
    return _BLANK_RUN_RE.sub("\n\n", "\n".join(kept)).strip("\n")


def extract_policy(pdf_path: Path) -> PolicyText:
    """Read the policy PDF into one clean text, remembering where each page starts."""
    reader = PdfReader(pdf_path)
    parts: list[str] = []
    starts: list[int] = []
    offset = 0
    for page in reader.pages:
        cleaned = clean_page(page.extract_text(extraction_mode="layout"))
        cleaned = cleaned.replace(EMAIL_TYPO, EMAIL_FIX)
        starts.append(offset)
        parts.append(cleaned)
        offset += len(cleaned) + len(PAGE_SEPARATOR)
    return PolicyText(text=PAGE_SEPARATOR.join(parts), page_starts=tuple(starts))
