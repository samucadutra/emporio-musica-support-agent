"""Input and output models for every tool (design §6).

Field descriptions on Input models become the JSON schema the model sees.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from emporio_musica_support_agent.data.cleaning import Availability
from emporio_musica_support_agent.data.models import OrderStatus, ProductStatus
from emporio_musica_support_agent.domain.windows import ReturnWindows
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


class ProductDetailsInput(BaseModel):
    product_id: int | None = Field(
        None, description="Product ID, if known from an earlier tool result."
    )
    name: str | None = Field(
        None, description="Product name as the customer wrote it, e.g. 'Takamine GD20'."
    )

    @model_validator(mode="after")
    def check_product_given(self) -> Self:
        if self.name is not None and not self.name.strip():
            self.name = None
        if self.product_id is None and self.name is None:
            raise ValueError("give product_id or name")
        return self


class InstallmentOption(BaseModel):
    n: int
    value: Money
    allowed: bool
    min_required: Money  # minimum installment value for n (policy §3.1)


class Installments(BaseModel):
    max_installments: int  # largest n allowed by A-11
    installment_value: Money  # value at max_installments
    options: list[InstallmentOption]  # n = 1..12


class ProductDetails(ProductSummary):
    status: ProductStatus
    in_stock: bool
    pix_price: Money | None  # None when a promotion is current (§6.2)
    installments: Installments  # computed on the final price
    inactive_promotions: list[str]  # campaign names, e.g. ["Oferta Especial (12%)"]
    description_reliable: bool
    description: str | None  # None when not reliable (A-07)
    specs: dict[str, str | int] | None
    alternatives: list[ProductSummary] = []  # up to 3, only when not "disponível"


class ProductDetailsResult(BaseModel):
    found: bool
    product: ProductDetails | None = None
    candidates: list[ProductSummary] = []  # ambiguous or fuzzy name: ask which one


class OrderStatusInput(BaseModel):
    order_id: int = Field(ge=1, description="Order number given by the customer.")
    email: str | None = Field(None, description="Email the customer gave, exactly as typed.")
    phone: str | None = Field(None, description="Phone the customer gave, exactly as typed.")

    @model_validator(mode="after")
    def check_contact_given(self) -> Self:
        if self.email is not None and not self.email.strip():
            self.email = None
        if self.phone is not None and not self.phone.strip():
            self.phone = None
        if self.email is None and self.phone is None:
            raise ValueError("ask the customer for the email or phone used in the purchase")
        return self


class OrderItemOut(BaseModel):
    product_id: int
    name: str
    quantity: int


class VerifiedOrder(BaseModel):
    order_id: int
    customer_first_name: str
    status: OrderStatus
    status_label: str  # "pendente", "confirmado", "enviado", "entregue", "cancelado"
    order_date: date
    items: list[OrderItemOut]
    total: Money  # as charged (A-16)
    payment: str  # "cartão de crédito em 3x"
    tracking_code: str | None
    estimated_delivery: date | None
    is_late: bool  # shipped and estimated_delivery < reference date
    notes: str | None  # cancellation reason
    windows: ReturnWindows | None
    windows_note: str | None  # why windows is None


class OrderStatusResult(BaseModel):
    verified: bool
    order: VerifiedOrder | None = None
    message: str | None = None  # "not_found_or_not_verified" when verified is False


class OpeningHours(BaseModel):
    days: str  # "Segunda a Sexta-feira"
    hours: str  # "09:00 às 18:00" | "Fechado"


class StoreInfo(BaseModel):
    name: str
    address: str
    phone: str
    whatsapp: str
    email: str
    hours: list[OpeningHours]
    hours_note: str  # extended hours on special dates (§2)
    holiday_note: str
    timezone: str  # "America/Campo_Grande"
    local_datetime: datetime  # real clock, tz-aware (A-03)
    weekday: str  # "sábado"
    open_now: bool
    next_opening: datetime | None  # when closed
    closes_at: datetime | None  # when open
    source_sections: list[str]  # ["1.2", "2", "7"]


HandoffReason = Literal["complaint", "cancellation", "return", "freight_quote", "unknown", "other"]


class HandoffInput(BaseModel):
    reason: HandoffReason
    summary: str = Field(
        max_length=500,
        description=(
            "One or two sentences for the team: what the customer needs. "
            "Do not include email or phone."
        ),
    )
    order_id: int | None = Field(
        None, ge=1, description="Only if the order was verified in this conversation."
    )


class HandoffTicket(BaseModel):
    ticket_id: str  # "EMP-20260323-7F3A"
    created_at: datetime
    reason: HandoffReason
    whatsapp: str
    phone: str
    hours: list[OpeningHours]
    team_available_now: bool
    next_opening: datetime | None
    response_time_note: str | None  # complaints only (§7.3)


class CategorySummary(BaseModel):
    category_id: int
    name: str
    description: str
    available_count: int  # products "disponível"


class CategoryListResult(BaseModel):
    categories: list[CategorySummary]
