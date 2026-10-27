"""Promotion queries and pricing rules (design §6.2, A-05, A-11)."""

from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from emporio_musica_support_agent.data.loader import StoreData, load_store_data
from emporio_musica_support_agent.data.models import Category, Product, Promotion
from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.domain.pricing import (
    final_price,
    installment_minimum,
    installment_options,
    max_installments,
    pix_price,
)


def priced(repo: Repository, product_id: int) -> tuple[Product, Promotion | None, Decimal]:
    product = repo.get_product(product_id)
    assert product is not None
    promotion = repo.current_promotion(product_id)
    return product, promotion, final_price(product.price_brl, promotion)


def test_takamine_gd20_without_promotion(repo: Repository) -> None:
    product, promotion, final = priced(repo, 95)
    twelve = installment_options(final)[11]

    assert promotion is None
    assert final == Decimal("2199.00")
    assert pix_price(product.price_brl, promotion) == Decimal("2089.05")
    assert (twelve.n, twelve.value, twelve.allowed) == (12, Decimal("183.25"), True)
    assert max_installments(final) == 12


def test_takamine_gd20_lists_expired_promotion(repo: Repository) -> None:
    inactive = repo.inactive_promotions(95)

    assert [(p.promotion_id, p.description, p.discount_percent) for p in inactive] == [
        (4, "Oferta Especial", 12)
    ]


def test_ohana_ck20_promotion_and_no_pix(repo: Repository) -> None:
    product, promotion, final = priced(repo, 121)

    assert promotion is not None
    assert (promotion.promotion_id, promotion.discount_percent) == (14, 20)
    assert final == Decimal("439.20")
    assert pix_price(product.price_brl, promotion) is None
    assert max_installments(final) == 5


def test_yamaha_c40_max_six_installments(repo: Repository) -> None:
    _, _, final = priced(repo, 81)
    options = installment_options(final)

    assert max_installments(final) == 6
    assert options[5].value == Decimal("99.98")
    assert (options[6].value, options[6].minimum, options[6].allowed) == (
        Decimal("85.70"),
        Decimal(100),
        False,
    )


@pytest.mark.parametrize(
    ("n", "minimum"), [(1, 50), (3, 50), (4, 80), (6, 80), (7, 100), (12, 100)]
)
def test_installment_minimum_tiers(n: int, minimum: int) -> None:
    assert installment_minimum(n) == Decimal(minimum)


@pytest.mark.parametrize("n", [0, 13])
def test_installment_minimum_out_of_range(n: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 12"):
        installment_minimum(n)


def test_one_installment_always_allowed() -> None:
    options = installment_options(Decimal("30.00"))

    assert options[0].allowed
    assert max_installments(Decimal("30.00")) == 1


def test_allowed_options_are_a_prefix_for_every_product(repo: Repository) -> None:
    for product in repo.search_products(only_available=False):
        final = final_price(product.price_brl, repo.current_promotion(product.product_id))
        options = installment_options(final)
        allowed = [o.n for o in options if o.allowed]

        assert [o.n for o in options] == list(range(1, 13))
        assert allowed == list(range(1, max_installments(final) + 1))
        assert all(o.value.as_tuple().exponent == -2 for o in options)


def test_at_most_one_current_promotion_per_product(repo: Repository, data_dir: Path) -> None:
    promotions = load_store_data(data_dir).promotions
    active_counts = Counter(p.product_id for p in promotions if p.is_active)

    for product in repo.search_products(only_available=False):
        promotion = repo.current_promotion(product.product_id)
        if product.availability == "disponível":
            assert active_counts[product.product_id] <= 1
            assert (promotion is not None) == (active_counts[product.product_id] == 1)
        else:
            assert promotion is None


def test_promotion_on_out_of_stock_product_is_not_current() -> None:
    product = Product(
        product_id=1,
        name="Violão Teste",
        category_id=5,
        price_brl=Decimal(1000),
        description=None,
        stock_quantity=0,
        status="active",
        specs={},
        created_at=date(2026, 1, 1),
    )
    promotion = Promotion(
        promotion_id=1, product_id=1, discount_percent=10, description="Teste", is_active=True
    )
    repo = Repository(
        StoreData(
            categories=(Category(category_id=5, name="Violões", description=""),),
            products=(product,),
            promotions=(promotion,),
            orders=(),
            order_items=(),
            customers=(),
        )
    )

    assert repo.current_promotion(1) is None
    assert repo.inactive_promotions(1) == []
