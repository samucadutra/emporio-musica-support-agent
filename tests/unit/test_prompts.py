"""The Lia system prompt (design §9)."""

import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from emporio_musica_support_agent.agent.prompts import (
    PROMPT_VERSION,
    SIMULATED_NOTE,
    SYSTEM_PROMPT,
    build_system_prompt,
)
from emporio_musica_support_agent.clock import FixedClock
from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.domain import store

DESIGN = Path(__file__).parents[2] / "docs" / "design.md"
CLOCK = FixedClock(datetime(2026, 2, 20, 23, 30, tzinfo=ZoneInfo("America/Campo_Grande")))


def test_template_is_design_section_9_verbatim() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    section = design[design.index("## 9. Prompt strategy") : design.index("## 10. Persistence")]
    block = re.search(r"```text\n(.*?)\n```", section, re.S)

    assert block is not None
    assert SYSTEM_PROMPT.strip("\n") == block.group(1)
    assert PROMPT_VERSION


def test_store_today_gives_simulated_reference_date() -> None:
    prompt = build_system_prompt(Settings(_env_file=None, store_today=date(2026, 3, 23)), CLOCK)

    assert "Reference date: 2026-03-23 (segunda-feira)" in prompt
    assert SIMULATED_NOTE in prompt


def test_clock_date_in_store_timezone_without_note() -> None:
    prompt = build_system_prompt(Settings(_env_file=None, store_today=None), CLOCK)

    # 23:30 in Campo Grande is already the 21st in UTC; the store date must win.
    assert "Reference date: 2026-02-20 (sexta-feira)" in prompt
    assert SIMULATED_NOTE not in prompt


def test_no_placeholders_left() -> None:
    prompt = build_system_prompt(Settings(_env_file=None), CLOCK)

    assert "{" not in prompt
    assert "}" not in prompt


@pytest.mark.parametrize(
    "fact", [store.ADDRESS, store.PHONE, store.WHATSAPP, store.EMAIL, "Rua 14", "3341", "3321"]
)
def test_template_has_no_store_contacts(fact: str) -> None:
    assert fact not in SYSTEM_PROMPT
