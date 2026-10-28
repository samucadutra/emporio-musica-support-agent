from pathlib import Path

import pytest

from emporio_musica_support_agent.evals.cases import (
    EvalCase,
    EvalCaseError,
    Expect,
    check_expectations,
    load_cases,
)
from emporio_musica_support_agent.tools.registry import TOOL_NAMES

CASES_FILE = Path(__file__).parents[2] / "evals" / "cases.yaml"


def make_case(**expect: object) -> EvalCase:
    return EvalCase(id="c", description="d", turns=["oi"], expect=Expect(**expect))  # type: ignore[arg-type]


def test_cases_file_has_15_unique_cases() -> None:
    cases = load_cases(CASES_FILE)
    assert len(cases) == 15
    assert len({c.id for c in cases}) == 15


def test_cases_only_name_registered_tools() -> None:
    for case in load_cases(CASES_FILE):
        names = {*case.expect.must_call, *case.expect.must_not_call}
        assert names <= set(TOOL_NAMES), case.id


def test_order_cases_forbid_customer_contacts() -> None:
    by_id = {c.id: c for c in load_cases(CASES_FILE)}
    for case_id in ("return-order-7-inside-window", "order-8-late", "cancel-order-13-handoff"):
        assert any("@" in text for text in by_id[case_id].expect.must_not_include), case_id


def test_substring_check_ignores_case_and_accents() -> None:
    case = make_case(must_include=["devolução"])
    assert check_expectations(case, [], ["Pode DEVOLUCAO sim"]) == []
    assert check_expectations(case, [], ["não"]) == ["missing 'devolução'"]


def test_include_any_needs_one_per_group() -> None:
    case = make_case(must_include_any=[["a1", "b2"], ["c3"]])
    assert check_expectations(case, [], ["b2 c3"]) == []
    assert len(check_expectations(case, [], ["b2"])) == 1


def test_must_not_include_and_regex() -> None:
    case = make_case(must_not_include=["segredo"], regex=[r"r\$ \d+,\d{2}"])
    assert check_expectations(case, [], ["Custa R$ 10,50"]) == []
    failures = check_expectations(case, [], ["Segredo: dez reais"])
    assert len(failures) == 2


def test_scope_last_vs_all() -> None:
    first_only = ["tem 4.1 aqui", "outra coisa"]
    assert check_expectations(make_case(must_include=["4.1"]), [], first_only)
    assert check_expectations(make_case(must_include=["4.1"], scope="all"), [], first_only) == []
    leak = make_case(must_not_include=["a@b.com"], scope="all")
    assert check_expectations(leak, [], ["a@b.com", "ok"])


def test_tool_expectations() -> None:
    case = make_case(must_call=["search_policies"], must_not_call=["request_human_handoff"])
    assert check_expectations(case, ["search_policies"], ["x"]) == []
    failures = check_expectations(case, ["request_human_handoff"], ["x"])
    assert failures == ["did not call search_policies", "called request_human_handoff"]


def test_loader_rejects_duplicates_bad_regex_and_naive_clock(tmp_path: Path) -> None:
    def write(body: str) -> Path:
        path = tmp_path / "cases.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    one = "- id: a\n  description: d\n  turns: [oi]\n  expect: {}\n"
    with pytest.raises(EvalCaseError, match="duplicate"):
        load_cases(write(one + one))
    with pytest.raises(EvalCaseError):
        load_cases(write(one.replace("{}", "{regex: ['(']}")))
    with pytest.raises(EvalCaseError):
        load_cases(write(one.replace("expect", "clock: 2026-03-23T10:00:00\n  expect")))
    with pytest.raises(EvalCaseError):
        load_cases(tmp_path / "missing.yaml")
