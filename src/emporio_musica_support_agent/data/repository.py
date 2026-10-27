"""In-memory store repository: indexes, catalogue search and name lookup (design §5.3–5.4)."""

import re
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

from emporio_musica_support_agent.data.loader import StoreData, load_store_data
from emporio_musica_support_agent.data.models import (
    Category,
    Customer,
    Order,
    OrderItem,
    Product,
    Promotion,
)
from emporio_musica_support_agent.text import fold

# Folded instrument words -> category ID (design §5.3).
CATEGORY_ALIASES: dict[str, int] = {
    "guitarra": 1,
    "guitarras": 1,
    "guitarra eletrica": 1,
    "baixo": 2,
    "baixos": 2,
    "contrabaixo": 2,
    "baixo eletrico": 2,
    "bateria": 3,
    "baterias": 3,
    "percussao": 3,
    "teclado": 4,
    "teclados": 4,
    "piano": 4,
    "sintetizador": 4,
    "synth": 4,
    "violao": 5,
    "violoes": 5,
    "sopro": 6,
    "saxofone": 6,
    "sax": 6,
    "flauta": 6,
    "clarinete": 6,
    "oboe": 6,
    "trompete": 7,
    "trombone": 7,
    "tuba": 7,
    "trompa": 7,
    "violino": 8,
    "viola": 8,
    "violoncelo": 8,
    "cello": 8,
    "ukulele": 9,
    "ukuleles": 9,
    "uke": 9,
}
STOP_WORDS: frozenset[str] = frozenset({"de", "da", "do", "para", "com", "e", "ate", "reais", "r$"})
MAX_NAME_CANDIDATES = 5
FUZZY_CUTOFF = 0.6

# Feature words in folded product names, weighted for "similar product" ranking (design §5.4).
# Names say "Cedar"; "cedro" only appears in descriptions, so both are listed.
FEATURE_WEIGHTS: dict[str, int] = {
    "7 cordas": 2,
    "dreadnought": 2,
    "folk": 2,
    "jumbo": 2,
    "classico": 2,
    "concert": 2,
    "soprano": 2,
    "tenor": 2,
    "baritono": 2,
    "nylon": 1,
    "aco": 1,
    "eletrico": 1,
    "cedro": 1,
    "cedar": 1,
    "mogno": 1,
}
PRICE_BAND = Decimal("0.6")  # alternatives within ±60% of the product's list price come first

# "ate 1000", "ate r$ 1.000,00", "ate r$1000 reais" in folded text.
_PRICE_CAP_RE = re.compile(
    r"\bate\s+(?:r\$\s*)?(?P<int>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<cents>\d{1,2}))?(?:\s*reais)?"
)
_TOKEN_PUNCTUATION = ".,;:!?()\"'"


@dataclass(frozen=True)
class ParsedQuery:
    tokens: tuple[str, ...]  # folded, 2+ characters, stop words removed
    category_id: int | None  # from alias words, when they point to exactly one category
    max_price: Decimal | None  # from "até N"


@dataclass(frozen=True)
class NameLookup:
    match: Product | None
    candidates: tuple[Product, ...]


def _tokens(folded: str) -> list[str]:
    stripped = (t.strip(_TOKEN_PUNCTUATION) for t in folded.split())
    return [t for t in stripped if t]


def _compact(folded: str) -> str:
    return folded.replace(" ", "")


def _features(folded_name: str) -> frozenset[str]:
    """Feature words present as whole words, so "aco" never matches "acustica"."""
    padded = f" {folded_name} "
    return frozenset(word for word in FEATURE_WEIGHTS if f" {word} " in padded)


def parse_query(query: str) -> ParsedQuery:
    """Split free text into match tokens, an implied category and an "até N" price cap."""
    folded = fold(query)

    max_price = None
    if price := _PRICE_CAP_RE.search(folded):
        integer = price.group("int").replace(".", "")
        max_price = Decimal(f"{integer}.{price.group('cents') or '0'}")
        folded = folded[: price.start()] + " " + folded[price.end() :]

    words = _tokens(folded)
    alias_categories: set[int] = set()
    alias_positions: set[int] = set()
    i = 0
    while i < len(words):
        bigram = " ".join(words[i : i + 2])
        if i + 1 < len(words) and bigram in CATEGORY_ALIASES:
            alias_categories.add(CATEGORY_ALIASES[bigram])
            alias_positions.update((i, i + 1))
            i += 2
        elif words[i] in CATEGORY_ALIASES:
            alias_categories.add(CATEGORY_ALIASES[words[i]])
            alias_positions.add(i)
            i += 1
        else:
            i += 1

    # One instrument word is a category filter; matching it as text would also hit
    # products that merely mention it (ukulele 128's description mentions "violão").
    category_id = None
    if len(alias_categories) == 1:
        category_id = alias_categories.pop()
        words = [w for i, w in enumerate(words) if i not in alias_positions]

    tokens = tuple(w for w in words if len(w) >= 2 and w not in STOP_WORDS)
    return ParsedQuery(tokens=tokens, category_id=category_id, max_price=max_price)


class Repository:
    """Read-only indexes over the store data, built once at start-up (A-17)."""

    def __init__(self, data: StoreData) -> None:
        # The raw rows, for start-up validation only; tools use the query methods.
        self.data = data
        self._categories = {c.category_id: c for c in data.categories}
        self._products = {p.product_id: p for p in data.products}
        self._orders = {o.order_id: o for o in data.orders}
        self._customers = {c.customer_id: c for c in data.customers}
        self._order_items: dict[int, list[OrderItem]] = {}
        for item in data.order_items:
            self._order_items.setdefault(item.order_id, []).append(item)
        self._promotions: dict[int, list[Promotion]] = {}
        for promotion in sorted(data.promotions, key=lambda p: p.promotion_id):
            self._promotions.setdefault(promotion.product_id, []).append(promotion)

        aliases_by_category: dict[int, list[str]] = {}
        for alias, category_id in CATEGORY_ALIASES.items():
            aliases_by_category.setdefault(category_id, []).append(alias)
        self._category_by_name = {fold(c.name): c for c in data.categories}

        self._folded_names = {p.product_id: fold(p.name) for p in data.products}
        self._compact_names = {pid: _compact(n) for pid, n in self._folded_names.items()}
        self._features = {pid: _features(n) for pid, n in self._folded_names.items()}
        self._search_text: dict[int, str] = {}
        for p in data.products:
            category = self._categories.get(p.category_id)
            parts = [p.name, category.name if category else ""]
            parts += aliases_by_category.get(p.category_id, [])
            # Descriptions of 135–144 contradict their names (issue #4 / D4).
            if p.description_reliable and p.description:
                parts.append(p.description)
            self._search_text[p.product_id] = fold(" ".join(parts))

    @classmethod
    def load(cls, data_dir: Path) -> "Repository":
        return cls(load_store_data(data_dir))

    def categories(self) -> list[Category]:
        return sorted(self._categories.values(), key=lambda c: c.category_id)

    def resolve_category(self, text_or_id: str | int) -> Category | None:
        """Find a category by ID, name or instrument word ("violões", "saxofone")."""
        if isinstance(text_or_id, int):
            return self._categories.get(text_or_id)
        key = fold(text_or_id)
        if key.isdigit():
            return self._categories.get(int(key))
        if key in self._category_by_name:
            return self._category_by_name[key]
        category_id = CATEGORY_ALIASES.get(key)
        return self._categories.get(category_id) if category_id is not None else None

    def get_product(self, product_id: int) -> Product | None:
        return self._products.get(product_id)

    def current_promotion(self, product_id: int) -> Promotion | None:
        """The active promotion, only while the product can be bought (A-05)."""
        product = self._products.get(product_id)
        if product is None or product.availability != "disponível":
            return None
        active = (p for p in self._promotions.get(product_id, []) if p.is_active)
        return next(active, None)

    def inactive_promotions(self, product_id: int) -> list[Promotion]:
        """Ended promotions (`is_active == 0`). An active promotion on an unavailable
        product is on hold, not ended, so it isn't listed here."""
        return [p for p in self._promotions.get(product_id, []) if not p.is_active]

    def alternatives_for(self, product: Product, n: int = 3) -> list[Product]:
        """Up to `n` available products in the same category, most similar first.

        Ranked by shared feature words, then by price difference. Products within
        ±60% of the price come first; the list is filled from outside that band
        only when the band has fewer than `n`.
        """
        features = self._features[product.product_id]

        def rank(other: Product) -> tuple[int, Decimal, int]:
            score = sum(FEATURE_WEIGHTS[w] for w in features & self._features[other.product_id])
            return -score, abs(other.price_brl - product.price_brl), other.product_id

        pool = [
            p
            for p in self._products.values()
            if p.category_id == product.category_id
            and p.product_id != product.product_id
            and p.availability == "disponível"
        ]
        low = product.price_brl * (1 - PRICE_BAND)
        high = product.price_brl * (1 + PRICE_BAND)
        in_band = sorted((p for p in pool if low <= p.price_brl <= high), key=rank)
        outside = sorted((p for p in pool if not low <= p.price_brl <= high), key=rank)
        return (in_band + outside)[:n]

    def get_order(self, order_id: int) -> Order | None:
        return self._orders.get(order_id)

    def get_order_items(self, order_id: int) -> list[OrderItem]:
        return list(self._order_items.get(order_id, []))

    def get_customer(self, customer_id: int) -> Customer | None:
        """For contact verification only; no tool output contains a Customer."""
        return self._customers.get(customer_id)

    def _matches_tokens(self, product_id: int, tokens: tuple[str, ...], text: str) -> bool:
        compact = self._compact_names[product_id]
        return all(t in text or t in compact for t in tokens)

    def search_products(
        self,
        *,
        query: str | None = None,
        category_id: int | None = None,
        brand: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        only_available: bool = True,
    ) -> list[Product]:
        """Filter the catalogue; sorted by list price, then name.

        Explicit `category_id` and `max_price` win over what `query` implies.
        """
        tokens: tuple[str, ...] = ()
        if query:
            parsed = parse_query(query)
            tokens = parsed.tokens
            category_id = category_id if category_id is not None else parsed.category_id
            max_price = max_price if max_price is not None else parsed.max_price
        folded_brand = fold(brand) if brand else None

        results = [
            p
            for p in self._products.values()
            if (category_id is None or p.category_id == category_id)
            and (folded_brand is None or folded_brand in self._folded_names[p.product_id])
            and (min_price is None or p.price_brl >= min_price)
            and (max_price is None or p.price_brl <= max_price)
            and (not only_available or p.availability == "disponível")
            and self._matches_tokens(p.product_id, tokens, self._search_text[p.product_id])
        ]
        return sorted(results, key=lambda p: (p.price_brl, p.name))

    def find_products_by_name(self, name: str) -> NameLookup:
        """Exact name, then every token in the name, then fuzzy candidates (never a match)."""
        query = fold(name)
        tokens = tuple(_tokens(query))
        if not tokens:
            return NameLookup(match=None, candidates=())

        for product_id, folded in self._folded_names.items():
            if folded == query:
                return NameLookup(match=self._products[product_id], candidates=())

        hits = [
            p
            for p in self._products.values()
            if self._matches_tokens(p.product_id, tokens, self._folded_names[p.product_id])
        ]
        if len(hits) == 1:
            return NameLookup(match=hits[0], candidates=())
        if hits:
            ranked = sorted(hits, key=lambda p: p.name)
            return NameLookup(match=None, candidates=tuple(ranked[:MAX_NAME_CANDIDATES]))

        # Compare with an equally long prefix of each name: whole names are much
        # longer than a typed model name, which would sink every ratio.
        compact_query = _compact(" ".join(tokens))
        scored = []
        for product_id, compact in self._compact_names.items():
            ratio = SequenceMatcher(None, compact_query, compact[: len(compact_query)]).ratio()
            if ratio >= FUZZY_CUTOFF:
                scored.append((-ratio, product_id))
        candidates = tuple(self._products[pid] for _, pid in sorted(scored)[:MAX_NAME_CANDIDATES])
        return NameLookup(match=None, candidates=candidates)
