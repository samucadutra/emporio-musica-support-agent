"""Start-up validation of data and policy facts (design §5.5)."""

from dataclasses import replace
from pathlib import Path

import pytest

from emporio_musica_support_agent.data.loader import policy_path
from emporio_musica_support_agent.data.models import OrderItem, Promotion
from emporio_musica_support_agent.data.repository import Repository
from emporio_musica_support_agent.data.validation import DataValidationError, validate
from emporio_musica_support_agent.domain import store
from emporio_musica_support_agent.rag.extract import extract_policy


@pytest.fixture(scope="session")
def policy_text(data_dir: Path) -> str:
    return extract_policy(policy_path(data_dir)).text


def failures(repo: Repository, policy_text: str) -> list[str]:
    with pytest.raises(DataValidationError) as excinfo:
        validate(repo, policy_text)
    return excinfo.value.failures


def with_extra(repo: Repository, **extra: tuple[object, ...]) -> Repository:
    """A copy of the repository with rows appended to the named tables."""
    changes = {table: getattr(repo.data, table) + rows for table, rows in extra.items()}
    return Repository(replace(repo.data, **changes))


def test_real_data_passes(repo: Repository, policy_text: str) -> None:
    validate(repo, policy_text)


def test_orphan_order_item(repo: Repository, policy_text: str) -> None:
    broken = with_extra(repo, order_items=(OrderItem(order_id=7, product_id=9999, quantity=1),))

    found = failures(broken, policy_text)

    assert len(found) == 1
    assert "product_id 9999" in found[0]


def test_orphan_customer(repo: Repository, policy_text: str) -> None:
    order = repo.get_order(7)
    assert order is not None
    orphan = order.model_copy(update={"order_id": 99, "customer_id": 999})

    found = failures(with_extra(repo, orders=(orphan,)), policy_text)

    assert any("customer_id 999" in f for f in found)


def test_two_current_promotions(repo: Repository, policy_text: str) -> None:
    extra = Promotion(
        promotion_id=99, product_id=121, discount_percent=10, description="Teste", is_active=True
    )

    found = failures(with_extra(repo, promotions=(extra,)), policy_text)

    assert found == ["product 121: 2 current promotions (14, 99)"]


def test_unknown_enum_value(repo: Repository, policy_text: str) -> None:
    order = repo.get_order(7)
    assert order is not None
    # model_copy skips validation, like a row built outside the loader.
    lost = order.model_copy(update={"order_id": 98, "status": "lost"})

    found = failures(with_extra(repo, orders=(lost,)), policy_text)

    assert any("'lost'" in f for f in found)


def test_policy_missing_address(repo: Repository, policy_text: str) -> None:
    found = failures(repo, policy_text.replace(store.ADDRESS, ""))

    assert any("address" in f for f in found)


def test_policy_missing_window_length(repo: Repository, policy_text: str) -> None:
    assert "90\n(noventa)" in policy_text

    found = failures(repo, policy_text.replace("90\n(noventa)", ""))

    assert found == ["policy: 90-day window not found"]


def test_all_failures_reported_together(repo: Repository, policy_text: str) -> None:
    broken = with_extra(repo, order_items=(OrderItem(order_id=7, product_id=9999, quantity=1),))

    with pytest.raises(DataValidationError) as excinfo:
        validate(broken, policy_text.replace(store.ADDRESS, ""))
    message = str(excinfo.value)

    assert len(excinfo.value.failures) >= 2
    assert message.startswith("data validation failed")
    assert "- order_items: product_id 9999" in message
    assert "- policy: store address" in message
