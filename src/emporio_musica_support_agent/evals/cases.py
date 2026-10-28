"""Agent eval cases: YAML schema, loader and deterministic checks (design §13)."""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from emporio_musica_support_agent.text import fold


class EvalCaseError(ValueError):
    """The cases file is unreadable, invalid or has duplicate IDs."""


class Expect(BaseModel):
    """What a case must show. Text checks are accent- and case-insensitive.

    Regexes run on the folded reply (lowercase, no accents), so write them that way.
    `scope` picks the reply the text checks run on: the last one, or all of them.
    """

    must_call: list[str] = []
    must_not_call: list[str] = []
    must_include: list[str] = []
    must_include_any: list[list[str]] = []
    must_not_include: list[str] = []
    regex: list[str] = []
    scope: Literal["last", "all"] = "last"

    @field_validator("regex")
    @classmethod
    def _compile(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"invalid regex {pattern!r}: {error}") from error
        return patterns


class EvalCase(BaseModel):
    id: str
    description: str
    store_today: date | None = None
    clock: datetime | None = None
    turns: list[str] = Field(min_length=1)
    expect: Expect

    @field_validator("clock")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("clock must include a UTC offset, e.g. 2026-02-20T10:00:00-04:00")
        return value


def load_cases(path: Path) -> list[EvalCase]:
    """Read and validate a cases file. Raises EvalCaseError."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise EvalCaseError(f"cannot read {path}: {error}") from error
    if not isinstance(raw, list):
        raise EvalCaseError(f"{path} must contain a list of cases")
    try:
        cases = [EvalCase.model_validate(item) for item in raw]
    except ValidationError as error:
        raise EvalCaseError(f"invalid case in {path}: {error}") from error
    ids = [case.id for case in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise EvalCaseError(f"duplicate case IDs: {', '.join(duplicates)}")
    return cases


def check_expectations(case: EvalCase, tool_calls: list[str], replies: list[str]) -> list[str]:
    """Failure messages for a finished case; an empty list means it passed.

    `tool_calls` are tool names across the whole case.
    """
    expect = case.expect
    failures: list[str] = []
    failures += [f"did not call {name}" for name in expect.must_call if name not in tool_calls]
    failures += [f"called {name}" for name in expect.must_not_call if name in tool_calls]

    scoped = replies if expect.scope == "all" else replies[-1:]
    text = fold("\n".join(scoped))
    failures += [f"missing {item!r}" for item in expect.must_include if fold(item) not in text]
    failures += [
        f"none of {group!r} present"
        for group in expect.must_include_any
        if not any(fold(item) in text for item in group)
    ]
    failures += [
        f"forbidden text {item!r} present" for item in expect.must_not_include if fold(item) in text
    ]
    failures += [
        f"regex {pattern!r} did not match"
        for pattern in expect.regex
        if not re.search(pattern, text)
    ]
    return failures
