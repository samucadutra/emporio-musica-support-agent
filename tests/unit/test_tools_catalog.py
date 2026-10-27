"""search_products and list_categories tools (design §6.1, §6.3)."""

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.tools.catalog import list_categories, search_products
from emporio_musica_support_agent.tools.schemas import (
    Money,
    ProductSearchResult,
    SearchProductsInput,
)

# PRD §12 example 1, in price order.
VIOLOES_UP_TO_1000 = [83, 85, 89, 88, 81, 84, 87, 86, 107, 82, 91, 112]
SOPRO_MADEIRAS = "Instrumentos de Sopro (Madeiras)"


def search(repo: Repository, **kwargs: object) -> ProductSearchResult:
    return search_products(repo, SearchProductsInput(**kwargs))


def item_ids(result: ProductSearchResult) -> list[int]:
    return [item.product_id for item in result.items]


def test_violoes_up_to_1000(repo: Repository) -> None:
    result = search(repo, category="violões", max_price=1000)

    assert item_ids(result) == VIOLOES_UP_TO_1000
    assert (result.total, result.shown, result.truncated) == (12, 12, False)
    assert result.category_matched == "Violões"


def test_violoes_up_to_1000_from_free_text(repo: Repository) -> None:
    result = search(repo, query="violões até R$ 1000")

    assert item_ids(result) == VIOLOES_UP_TO_1000
    assert result.category_matched == "Violões"


def test_unavailable_included_on_request(repo: Repository) -> None:
    result = search(repo, category="violões", max_price=1000, only_available=False)
    labels = {item.product_id: item.availability for item in result.items}

    assert labels[96] == "temporariamente indisponível"
    assert labels[113] == "fora de catálogo"


def test_limit_truncates(repo: Repository) -> None:
    result = search(repo, category="violões", max_price=1000, limit=5)

    assert (result.total, result.shown, result.truncated) == (12, 5, True)
    assert item_ids(result) == VIOLOES_UP_TO_1000[:5]


@pytest.mark.parametrize("kwargs", [{"category": "saxofone"}, {"query": "saxofone"}])
def test_empty_category(repo: Repository, kwargs: dict[str, str]) -> None:
    result = search(repo, **kwargs)

    assert result.total == 0
    assert result.category_matched == SOPRO_MADEIRAS
    assert result.note == "category has no products"
    assert result.closest_matches == []


def test_unknown_category(repo: Repository) -> None:
    result = search(repo, category="xilofone")

    assert result.total == 0
    assert result.note is not None
    assert "unknown category" in result.note


def test_unknown_name_offers_closest_matches(repo: Repository) -> None:
    result = search(repo, query="Takamine GD2O")

    assert result.total == 0
    assert result.note == "no match; see closest_matches"
    assert result.closest_matches[0].product_id == 95


def test_promotion_fields(repo: Repository) -> None:
    result = search(repo, query="ohana ck20")
    promotion = result.items[0].promotion

    assert item_ids(result) == [121]
    assert promotion is not None
    assert (promotion.campaign, promotion.discount_percent) == ("Desconto Exclusivo", 20)
    assert promotion.original_price.fmt == "R$ 549,00"
    assert promotion.final_price.fmt == "R$ 439,20"


def test_no_promotion_on_takamine(repo: Repository) -> None:
    result = search(repo, query="Takamine GD20")

    assert item_ids(result) == [95]
    assert result.items[0].promotion is None


@pytest.mark.parametrize(
    "kwargs",
    [{"min_price": 500, "max_price": 100}, {"max_price": -1}, {"limit": 31}, {"limit": 0}],
)
def test_invalid_input(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        SearchProductsInput(**kwargs)


def test_list_categories(repo: Repository) -> None:
    categories = {c.category_id: c for c in list_categories(repo).categories}

    assert sorted(categories) == list(range(1, 10))
    assert [categories[i].available_count for i in (6, 7, 8)] == [0, 0, 0]
    assert categories[5].available_count == len(repo.search_products(category_id=5))
    assert categories[5].available_count > 0


def test_money_from_decimal() -> None:
    assert Money.from_decimal(Decimal("2199")) == Money(brl=2199.0, fmt="R$ 2.199,00")
    assert Money.from_decimal(Decimal("599.9")).fmt == "R$ 599,90"


def test_json_output_omits_none(repo: Repository) -> None:
    payload = json.loads(search(repo, query="Takamine GD20").model_dump_json(exclude_none=True))

    assert "note" not in payload
    assert "promotion" not in payload["items"][0]
