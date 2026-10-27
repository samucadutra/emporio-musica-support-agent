"""Catalogue tools: search_products and list_categories (design §6.1, §6.3)."""

from decimal import Decimal

from emporio_musica_support_agent.data.models import Category, Product
from emporio_musica_support_agent.data.repository import Repository, parse_query
from emporio_musica_support_agent.domain.pricing import (
    final_price,
    installment_options,
    max_installments,
    pix_price,
)
from emporio_musica_support_agent.tools.schemas import (
    CategoryListResult,
    CategorySummary,
    InstallmentOption,
    Installments,
    Money,
    ProductDetails,
    ProductDetailsInput,
    ProductDetailsResult,
    ProductSearchResult,
    ProductSummary,
    PromotionInfo,
    SearchProductsInput,
)


def product_summary(repo: Repository, product: Product) -> ProductSummary:
    """Commercial summary of one product, with its current promotion if any."""
    category = repo.resolve_category(product.category_id)
    promotion = repo.current_promotion(product.product_id)
    promotion_info = None
    if promotion is not None:
        promotion_info = PromotionInfo(
            campaign=promotion.description,
            discount_percent=promotion.discount_percent,
            original_price=Money.from_decimal(product.price_brl),
            final_price=Money.from_decimal(final_price(product.price_brl, promotion)),
        )
    return ProductSummary(
        product_id=product.product_id,
        name=product.name,
        category=category.name if category else "",
        price=Money.from_decimal(product.price_brl),
        availability=product.availability,
        promotion=promotion_info,
    )


def _to_decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def search_products(repo: Repository, params: SearchProductsInput) -> ProductSearchResult:
    """Search the store catalogue. Use for questions like "what X do you have", "options under
    R$ N", "do you have brand Y", or when the customer names a product loosely. By default it
    returns only products that can be bought now, sorted by price. Price filters use the list
    price. Show at most the returned items, using `price.fmt` and, when `promotion` is set, the
    promotion fields. If `truncated` is true, offer to narrow the search. If `total` is 0, say
    nothing matching is available right now and offer `closest_matches` if any. Never mention
    products that are not in the result. For one product's price, installments or details, call
    `get_product_details` instead.
    """
    parsed = parse_query(params.query) if params.query else None

    category: Category | None = None
    if params.category is not None:
        category = repo.resolve_category(params.category)
        if category is None:
            return ProductSearchResult(
                total=0,
                shown=0,
                truncated=False,
                items=[],
                note=f"unknown category '{params.category}'; call list_categories",
            )
    elif parsed is not None and parsed.category_id is not None:
        category = repo.resolve_category(parsed.category_id)

    products = repo.search_products(
        query=params.query,
        category_id=category.category_id if category else None,
        brand=params.brand,
        min_price=_to_decimal(params.min_price),
        max_price=_to_decimal(params.max_price),
        only_available=params.only_available,
    )
    items = [product_summary(repo, p) for p in products[: params.limit]]

    note = None
    closest: list[ProductSummary] = []
    if not products:
        if category and not repo.search_products(
            category_id=category.category_id, only_available=False
        ):
            note = "category has no products"
        elif parsed is not None and parsed.tokens:
            lookup = repo.find_products_by_name(params.query or "")
            matches = [lookup.match] if lookup.match else list(lookup.candidates)
            closest = [product_summary(repo, p) for p in matches]
            note = "no match; see closest_matches" if closest else "no products match these filters"
        else:
            note = "no products match these filters"

    return ProductSearchResult(
        total=len(products),
        shown=len(items),
        truncated=len(products) > len(items),
        items=items,
        category_matched=category.name if category else None,
        note=note,
        closest_matches=closest,
    )


def _installments(final: Decimal) -> Installments:
    options = installment_options(final)
    best = max_installments(final)
    return Installments(
        max_installments=best,
        installment_value=Money.from_decimal(options[best - 1].value),
        options=[
            InstallmentOption(
                n=o.n,
                value=Money.from_decimal(o.value),
                allowed=o.allowed,
                min_required=Money.from_decimal(o.minimum),
            )
            for o in options
        ],
    )


def get_product_details(repo: Repository, params: ProductDetailsInput) -> ProductDetailsResult:
    """Get one product's price, promotion, PIX price, installments, availability and
    description. Use whenever the customer asks how much a product costs, whether it is in
    stock, about installments ("parcelar em 10x"), or about a promotion on it. Quote prices from
    the `fmt` fields exactly. If `promotion` is set, show original price, discount % and final
    price, and do NOT offer the PIX discount on top. Otherwise also give `pix_price`. For
    installments use `installments.max_installments` and `installment_value`. If the customer
    asks for more installments than allowed, say the maximum. If the customer asks about a
    promotion listed in `inactive_promotions`, say it is no longer active and give the current
    price. If `availability` is not "disponível", say so and offer the `alternatives`. If
    `description_reliable` is false, describe nothing beyond name, price and availability. If
    `found` is false and `candidates` is not empty, ask which one the customer means. If both are
    empty, say the product isn't in the catalogue.
    """
    if params.product_id is not None:
        product = repo.get_product(params.product_id)
        if product is None:
            return ProductDetailsResult(found=False)
    else:
        lookup = repo.find_products_by_name(params.name or "")
        if lookup.match is None:
            candidates = [product_summary(repo, p) for p in lookup.candidates]
            return ProductDetailsResult(found=False, candidates=candidates)
        product = lookup.match

    promotion = repo.current_promotion(product.product_id)
    pix = pix_price(product.price_brl, promotion)
    reliable = product.description_reliable
    alternatives = []
    if product.availability != "disponível":
        alternatives = [product_summary(repo, p) for p in repo.alternatives_for(product)]

    details = ProductDetails(
        **product_summary(repo, product).model_dump(),
        status=product.status,
        in_stock=product.stock_quantity > 0,
        pix_price=Money.from_decimal(pix) if pix is not None else None,
        installments=_installments(final_price(product.price_brl, promotion)),
        inactive_promotions=[
            f"{p.description} ({p.discount_percent}%)"
            for p in repo.inactive_promotions(product.product_id)
        ],
        description_reliable=reliable,
        # Descriptions and specs of 135–144 contradict their names (A-07).
        description=product.description if reliable else None,
        specs=dict(product.specs) if reliable else None,
        alternatives=alternatives,
    )
    return ProductDetailsResult(found=True, product=details)


def list_categories(repo: Repository) -> CategoryListResult:
    """List the instrument categories the store works with and how many products are available
    in each. Use for "what do you sell?" or to check whether a kind of instrument is available.
    A category with `available_count` 0 has nothing to buy right now; say so and don't invent
    items. The store sells instruments only, never accessories.
    """
    return CategoryListResult(
        categories=[
            CategorySummary(
                category_id=c.category_id,
                name=c.name,
                description=c.description,
                available_count=len(repo.search_products(category_id=c.category_id)),
            )
            for c in repo.categories()
        ]
    )
