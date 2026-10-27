"""CSV and policy file locations and loading (design §5.1)."""

import csv
from dataclasses import dataclass
from pathlib import Path

from emporio_musica_support_agent.data.models import (
    Category,
    Customer,
    Order,
    OrderItem,
    Product,
    Promotion,
)

# Explicit names, so the export prefix and `*:Zone.Identifier` files never matter (issue #17).
TABLE_FILES: dict[str, str] = {
    "categories": "desafio_tecnico_ai_eng - categories.csv",
    "products": "desafio_tecnico_ai_eng - products.csv",
    "promotions": "desafio_tecnico_ai_eng - promotions.csv",
    "orders": "desafio_tecnico_ai_eng - orders.csv",
    "order_items": "desafio_tecnico_ai_eng - order_items.csv",
    "customers": "desafio_tecnico_ai_eng - customers.csv",
}
POLICY_FILE = "políticas_da_loja.pdf"


class DataFileNotFoundError(FileNotFoundError):
    def __init__(self, table: str, path: Path) -> None:
        super().__init__(f"data file for {table!r} not found: {path}")
        self.table = table
        self.path = path


@dataclass(frozen=True)
class StoreData:
    categories: tuple[Category, ...]
    products: tuple[Product, ...]  # sorted by product_id (issue #13)
    promotions: tuple[Promotion, ...]
    orders: tuple[Order, ...]
    order_items: tuple[OrderItem, ...]
    customers: tuple[Customer, ...]


def _existing(table: str, path: Path) -> Path:
    if not path.is_file():
        raise DataFileNotFoundError(table, path)
    return path


def table_path(data_dir: Path, table: str) -> Path:
    return _existing(table, data_dir / TABLE_FILES[table])


def policy_path(data_dir: Path) -> Path:
    return _existing("policy", data_dir / POLICY_FILE)


def read_rows(data_dir: Path, table: str) -> list[dict[str, str]]:
    with table_path(data_dir, table).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_store_data(data_dir: Path) -> StoreData:
    """Read and validate every table. Raises DataFileNotFoundError for a missing CSV."""
    rows = {table: read_rows(data_dir, table) for table in TABLE_FILES}
    products = (Product.model_validate(r) for r in rows["products"])
    return StoreData(
        categories=tuple(Category.model_validate(r) for r in rows["categories"]),
        products=tuple(sorted(products, key=lambda p: p.product_id)),
        promotions=tuple(Promotion.model_validate(r) for r in rows["promotions"]),
        orders=tuple(Order.model_validate(r) for r in rows["orders"]),
        order_items=tuple(OrderItem.model_validate(r) for r in rows["order_items"]),
        customers=tuple(Customer.model_validate(r) for r in rows["customers"]),
    )
