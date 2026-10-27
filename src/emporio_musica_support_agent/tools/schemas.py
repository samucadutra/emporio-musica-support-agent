"""Input and output models for every tool (design §6).

Field descriptions on Input models become the JSON schema the model sees.
"""

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, model_validator

from emporio_musica_support_agent.data.cleaning import Availability
from emporio_musica_support_agent.text import format_brl, round_money


class Money(BaseModel):
    brl: float  # 2199.0
    fmt: str  # "R$ 2.199,00"; the model copies this string, never formats numbers itself

    @classmethod
    def from_decimal(cls, value: Decimal) -> "Money":
        return cls(brl=float(round_money(value)), fmt=format_brl(value))


class PromotionInfo(BaseModel):
    campaign: str  # "Desconto Exclusivo"
    discount_percent: int  # 20
    original_price: Money
    final_price: Money


class ProductSummary(BaseModel):
    product_id: int
    name: str
    category: str
    price: Money  # list price
    availability: Availability
    promotion: PromotionInfo | None = None


class SearchProductsInput(BaseModel):
    query: str | None = Field(
        None,
        description=(
            "Free text: instrument type, model, wood, color... e.g. 'violão nylon', 'cedro'."
        ),
    )
    category: str | None = Field(
        None,
        description="Category name or instrument word, e.g. 'violões', 'ukulele', 'saxofone'.",
    )
    brand: str | None = Field(None, description="Brand name, e.g. 'Yamaha'.")
    min_price: float | None = Field(None, ge=0, description="Minimum list price in BRL.")
    max_price: float | None = Field(
        None, ge=0, description="Maximum list price in BRL. 'até R$1000' -> 1000."
    )
    only_available: bool = Field(
        True,
        description=(
            "Keep True unless the customer explicitly asks about unavailable, "
            "discontinued or upcoming products."
        ),
    )
    limit: int = Field(15, ge=1, le=30)

    @model_validator(mode="after")
    def check_price_range(self) -> Self:
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.max_price < self.min_price
        ):
            raise ValueError("max_price must be >= min_price")
        return self


class ProductSearchResult(BaseModel):
    total: int  # matches before the limit
    shown: int
    truncated: bool  # total > shown: offer to narrow down
    items: list[ProductSummary]  # sorted by price ascending
    category_matched: str | None = None
    note: str | None = None
    closest_matches: list[ProductSummary] = []  # only when total == 0 and the query names a product


class CategorySummary(BaseModel):
    category_id: int
    name: str
    description: str
    available_count: int  # products "disponível"


class CategoryListResult(BaseModel):
    categories: list[CategorySummary]
