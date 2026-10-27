"""Repository indexes, catalogue search and name lookup (design §5.3–5.4)."""

from decimal import Decimal

import pytest

from emporio_musica_support_agent.data.repository import Repository, parse_query

# PRD §12 example 1: available violões up to R$ 1000, by price then name.
VIOLOES_UP_TO_1000 = [83, 85, 89, 88, 81, 84, 87, 86, 107, 82, 91, 112]


def ids(products: list) -> list[int]:
    return [p.product_id for p in products]


def test_violoes_up_to_1000_by_filters(repo: Repository) -> None:
    result = repo.search_products(category_id=5, max_price=Decimal(1000))

    assert ids(result) == VIOLOES_UP_TO_1000


@pytest.mark.parametrize("query", ["violao ate 1000", "violões até R$ 1.000,00"])
def test_violoes_up_to_1000_by_free_text(repo: Repository, query: str) -> None:
    assert ids(repo.search_products(query=query)) == VIOLOES_UP_TO_1000


def test_unavailable_products_only_on_request(repo: Repository) -> None:
    result = ids(repo.search_products(category_id=5, max_price=Decimal(1000), only_available=False))

    assert set(result) == {*VIOLOES_UP_TO_1000, 96, 113}


def test_description_words_match(repo: Repository) -> None:
    assert 84 in ids(repo.search_products(query="cedro"))


def test_unreliable_description_is_not_searched(repo: Repository) -> None:
    result = ids(repo.search_products(query="fender"))

    assert 135 not in result
    assert {134, 145} <= set(result)


def test_saxofone_is_an_empty_category(repo: Repository) -> None:
    category = repo.resolve_category("saxofone")

    assert category is not None
    assert category.category_id == 6
    assert repo.search_products(query="saxofone") == []
    assert repo.search_products(category_id=6, only_available=False) == []


@pytest.mark.parametrize("value", [5, "5", "Violões", "violoes"])
def test_resolve_category(repo: Repository, value: str | int) -> None:
    category = repo.resolve_category(value)

    assert category is not None
    assert category.category_id == 5


def test_unknown_category(repo: Repository) -> None:
    assert repo.resolve_category("xilofone") is None


def test_categories(repo: Repository) -> None:
    assert [c.category_id for c in repo.categories()] == list(range(1, 10))


def test_brand_filter_matches_anywhere_in_name(repo: Repository) -> None:
    result = repo.search_products(brand="yamaha")

    assert 139 in ids(result)  # "Bateria Acústica Yamaha Kit 1 Studio"
    assert all("yamaha" in p.name.casefold() for p in result)


def test_min_price_and_sorting(repo: Repository) -> None:
    result = repo.search_products(min_price=Decimal(5000))
    prices = [p.price_brl for p in result]

    assert result
    assert all(price >= 5000 for price in prices)
    assert prices == sorted(prices)


@pytest.mark.parametrize("query", ["Ohana CK-20", "ohana ck20"])
def test_model_names_match_with_or_without_separator(repo: Repository, query: str) -> None:
    assert ids(repo.search_products(query=query)) == [121]


def test_parse_query_extracts_category_and_price_cap() -> None:
    parsed = parse_query("violao ate 1000")

    assert parsed.tokens == ()
    assert parsed.category_id == 5
    assert parsed.max_price == Decimal(1000)


def test_parse_query_keeps_words_for_two_categories() -> None:
    parsed = parse_query("violao ou ukulele")

    assert parsed.category_id is None
    assert {"violao", "ukulele"} <= set(parsed.tokens)


@pytest.mark.parametrize("name", ["Takamine GD20", "Takamine GD20 Dreadnought Natural"])
def test_find_by_name_match(repo: Repository, name: str) -> None:
    lookup = repo.find_products_by_name(name)

    assert lookup.match is not None
    assert lookup.match.product_id == 95


def test_find_by_name_finds_discontinued(repo: Repository) -> None:
    lookup = repo.find_products_by_name("Shelby SN-7C")

    assert lookup.match is not None
    assert lookup.match.product_id == 113


def test_find_by_name_ambiguous_brand(repo: Repository) -> None:
    lookup = repo.find_products_by_name("yamaha")

    assert lookup.match is None
    assert len(lookup.candidates) >= 2
    assert all("Yamaha" in p.name for p in lookup.candidates)


def test_find_by_name_typo_gives_fuzzy_candidates(repo: Repository) -> None:
    lookup = repo.find_products_by_name("takamine gd2O")

    assert lookup.match is None
    assert lookup.candidates[0].product_id == 95


def test_find_by_name_unknown(repo: Repository) -> None:
    lookup = repo.find_products_by_name("violino stradivarius")

    assert lookup.match is None
    assert lookup.candidates == ()


def test_order_and_customer_getters(repo: Repository) -> None:
    order = repo.get_order(7)
    items = repo.get_order_items(7)

    assert order is not None
    assert order.customer_id == 14
    assert [(i.product_id, i.quantity) for i in items] == [(119, 1)]
    assert repo.get_customer(14) is not None
    assert repo.get_product(9999) is None
    assert repo.get_order(9999) is None
    assert repo.get_order_items(9999) == []
    assert repo.get_customer(9999) is None


def alternative_ids(repo: Repository, product_id: int, n: int = 3) -> list[int]:
    product = repo.get_product(product_id)
    assert product is not None
    return ids(repo.alternatives_for(product, n))


def test_alternatives_prefer_same_type(repo: Repository) -> None:
    # 113 Shelby SN-7C 7 Cordas Nylon: other 7-string guitars before cheaper look-alikes.
    assert alternative_ids(repo, 113) == [110, 112, 84]


def test_alternatives_for_out_of_stock_dreadnought(repo: Repository) -> None:
    assert alternative_ids(repo, 96)[0] == 91


def test_alternatives_match_cedar_in_names(repo: Repository) -> None:
    assert alternative_ids(repo, 130)[:2] == [129, 126]


def test_alternatives_filled_from_outside_price_band(repo: Repository) -> None:
    # 136 costs R$ 441; no available bass is within ±60%, so the closest prices fill in.
    bass = repo.get_product(136)
    assert bass is not None
    result = repo.alternatives_for(bass)

    assert len(result) == 3
    gaps = [abs(p.price_brl - bass.price_brl) for p in result]
    assert gaps == sorted(gaps)


def test_alternatives_respect_n(repo: Repository) -> None:
    assert alternative_ids(repo, 113, n=1) == [110]
    assert alternative_ids(repo, 113, n=0) == []


def test_alternatives_are_available_same_category_and_never_self(repo: Repository) -> None:
    for product in repo.search_products(only_available=False):
        result = repo.alternatives_for(product)

        assert len(result) <= 3
        assert product.product_id not in ids(result)
        assert all(p.availability == "disponível" for p in result)
        assert all(p.category_id == product.category_id for p in result)
