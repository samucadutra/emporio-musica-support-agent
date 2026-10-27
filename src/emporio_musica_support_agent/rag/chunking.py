"""Heading-aware chunking of the policy text (design §7, chunking).

One chunk per numbered subsection, so a chunk is one rule and its section
number is exactly what the agent cites (FR-06). No overlap: boundaries are
the policy's own headings, not arbitrary windows.
"""

from dataclasses import dataclass

from emporio_musica_support_agent.rag.extract import PolicyText

CHUNKER_VERSION = 1  # bump when these rules change; a new version makes the index stale
MAX_CHUNK_CHARS = 1800
COVER_NUMBER = "0"
COVER_TITLE = "Capa"

# Policy v2.1 headings in document order, verbatim. Matching an explicit list
# (not a "^\d+\." regex) keeps §7.2's numbered steps from starting chunks, and a
# heading missing from a new PDF version fails ingestion instead of mis-chunking.
POLICY_OUTLINE: tuple[tuple[str, str], ...] = (
    ("1", "Sobre a Empório da Música"),
    ("1.1", "Missão"),
    ("1.2", "Dados da Empresa"),
    ("2", "Horário de Funcionamento"),
    ("3", "Formas de Pagamento"),
    ("3.1", "Regras de Parcelamento"),
    ("4", "Política de Trocas e Devoluções"),
    ("4.1", "Direito de Arrependimento (Compras Online)"),
    ("4.2", "Trocas por Defeito"),
    ("4.3", "Trocas por Preferência"),
    ("4.4", "Itens Não Elegíveis para Troca"),
    ("5", "Política de Frete e Entregas"),
    ("5.1", "Entregas na Região Metropolitana de Campo Grande"),
    ("5.2", "Entregas para Outras Cidades"),
    ("5.3", "Código de Rastreamento"),
    ("6", "Promoções e Descontos"),
    ("6.1", "Tipos de Promoção"),
    ("6.2", "Regras de Promoções"),
    ("7", "Atendimento via WhatsApp"),
    ("7.1", "Diretrizes de Atendimento"),
    ("7.2", "Fluxo de Atendimento Padrão"),
    ("7.3", "Situações Especiais"),
    ("8", "Garantia"),
    ("8.1", "Garantia Legal"),
    ("8.2", "Garantia do Fabricante"),
    ("8.3", "O que Não Cobre a Garantia"),
    ("9", "Privacidade e Proteção de Dados"),
    ("10", "Disposições Finais"),
)


class PolicyOutlineError(ValueError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__("policy headings not found: " + "; ".join(missing))


@dataclass(frozen=True)
class Chunk:
    id: str  # "sec-4.1"; "sec-7.2-p2" when a section is split
    section_number: str
    section_title: str
    parent_title: str | None  # top-level title for "x.y" sections
    page: int  # page of the heading
    part: int  # 1..n
    heading: str  # heading line as in the policy ("" for the cover)
    body: str

    @property
    def text(self) -> str:
        """The stored document: heading line plus body."""
        return f"{self.heading}\n{self.body}" if self.heading else self.body

    @property
    def embedding_text(self) -> str:
        """Titles first, so they add retrieval signal."""
        title = f"Seção {self.section_number} — {self.section_title}"
        if self.parent_title:
            title += f" | {self.parent_title}"
        return f"{title}\n{self.body}"

    @property
    def metadata(self) -> dict[str, str | int]:
        """Vector-store metadata; Chroma doesn't accept None values."""
        return {
            "section_number": self.section_number,
            "section_title": self.section_title,
            "parent_title": self.parent_title or "",
            "page": self.page,
            "part": self.part,
            "chunker_version": CHUNKER_VERSION,
        }


def heading_line(number: str, title: str) -> str:
    """How a heading reads in the policy: "4. Título" (top level) or "4.1 Título"."""
    return f"{number} {title}" if "." in number else f"{number}. {title}"


def _pack(pieces: list[str], budget: int, separator: str) -> list[str]:
    """Greedily join pieces into groups no longer than `budget`."""
    groups: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{separator}{piece}" if current else piece
        if current and len(candidate) > budget:
            groups.append(current)
            current = piece
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups


def _split_body(body: str, budget: int) -> list[str]:
    """Split on paragraphs, then on lines for a paragraph that alone is too long."""
    pieces: list[str] = []
    for paragraph in body.split("\n\n"):
        if len(paragraph) <= budget:
            pieces.append(paragraph)
        else:
            pieces.extend(_pack(paragraph.split("\n"), budget, "\n"))
    return _pack(pieces, budget, "\n\n")


def _section_chunks(
    number: str,
    title: str,
    parent: str | None,
    page: int,
    heading: str,
    body: str,
    max_chars: int,
) -> list[Chunk]:
    whole = Chunk(f"sec-{number}", number, title, parent, page, 1, heading, body)
    if len(whole.text) <= max_chars:
        return [whole]
    heading_size = len(heading) + 1 if heading else 0
    parts = _split_body(body, max_chars - heading_size)
    return [
        Chunk(f"sec-{number}-p{i}", number, title, parent, page, i, heading, part)
        for i, part in enumerate(parts, start=1)
    ]


def chunk_policy(
    policy: PolicyText,
    outline: tuple[tuple[str, str], ...] = POLICY_OUTLINE,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[Chunk]:
    """Cover, intro and subsection chunks in document order.

    Raises PolicyOutlineError listing every outline heading not found as a whole
    line at column 0, in order.
    """
    lines = policy.text.split("\n")
    offsets = [0]
    for line in lines[:-1]:
        offsets.append(offsets[-1] + len(line) + 1)

    found: list[tuple[int, str, str]] = []  # (line index, number, title)
    missing: list[str] = []
    cursor = 0
    for number, title in outline:
        target = heading_line(number, title)
        index = next((i for i in range(cursor, len(lines)) if lines[i] == target), None)
        if index is None:
            missing.append(target)
            continue
        found.append((index, number, title))
        cursor = index + 1
    if missing:
        raise PolicyOutlineError(missing)

    titles = dict(outline)
    cover = "\n".join(lines[: found[0][0]]).strip("\n")
    chunks = _section_chunks(COVER_NUMBER, COVER_TITLE, None, 1, "", cover, max_chars)
    for position, (index, number, title) in enumerate(found):
        end = found[position + 1][0] if position + 1 < len(found) else len(lines)
        body = "\n".join(lines[index + 1 : end]).strip("\n")
        if not body:  # a top-level heading followed directly by its first subsection
            continue
        parent = titles[number.split(".")[0]] if "." in number else None
        chunks += _section_chunks(
            number,
            title,
            parent,
            policy.page_at(offsets[index]),
            lines[index],
            body,
            max_chars,
        )
    return chunks
