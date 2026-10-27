"""Validated, immutable rows of the store tables (design §5.1)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, field_validator, model_validator

from emporio_musica_support_agent.data.cleaning import (
    UNRELIABLE_DESCRIPTION_IDS,
    Availability,
    PaymentMethod,
    availability_label,
    empty_to_none,
    parse_payment_method,
    parse_specs,
)

ProductStatus = Literal["active", "discontinued", "coming_soon"]
OrderStatus = Literal["pending", "confirmed", "shipped", "delivered", "cancelled"]

# Optional CSV columns: an empty cell means missing.
OptionalStr = Annotated[str | None, BeforeValidator(empty_to_none)]
OptionalDate = Annotated[date | None, BeforeValidator(empty_to_none)]


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True)


class Category(_Row):
    category_id: int
    name: str
    description: str


class Product(_Row):
    product_id: int
    name: str
    category_id: int
    price_brl: Decimal
    description: OptionalStr
    stock_quantity: int
    status: ProductStatus
    specs: dict[str, str | int]
    created_at: date

    @field_validator("specs", mode="before")
    @classmethod
    def specs_from_json(cls, value: object) -> object:
        return parse_specs(value) if isinstance(value, str) else value

    @property
    def description_reliable(self) -> bool:
        return self.product_id not in UNRELIABLE_DESCRIPTION_IDS

    @property
    def availability(self) -> Availability:
        return availability_label(self.status, self.stock_quantity)


class Promotion(_Row):
    promotion_id: int
    product_id: int
    discount_percent: int
    description: str  # campaign name, e.g. "Black Friday"
    is_active: bool


class Payment(_Row):
    method: PaymentMethod
    installments: int
    label: str  # pt-BR, e.g. "cartão de crédito em 12x"


class Order(_Row):
    order_id: int
    customer_id: int
    order_date: date
    status: OrderStatus
    total_brl: Decimal  # as charged; never recomputed (A-16)
    payment_method: str  # raw value, e.g. "credit_12x"
    payment: Payment
    tracking_code: OptionalStr
    estimated_delivery: OptionalDate
    notes: OptionalStr

    @model_validator(mode="before")
    @classmethod
    def split_payment_method(cls, data: Any) -> Any:
        if isinstance(data, dict) and "payment" not in data and "payment_method" in data:
            method, installments, label = parse_payment_method(data["payment_method"])
            data = {
                **data,
                "payment": {"method": method, "installments": installments, "label": label},
            }
        return data


class OrderItem(_Row):
    order_id: int
    product_id: int
    quantity: int


class Customer(_Row):
    customer_id: int
    name: str
    phone: str
    email: str
    city: str
