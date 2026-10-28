# CLAUDE.md

## Project purpose

Take-home challenge for an AI Engineer role (statement: `docs/challenge.pdf`).
A Python customer-support agent for a fictional music store, Empório da Música.
It answers questions using the store's data (`data/*.csv`) and policies (`data/políticas_da_loja.pdf`).

## Working method: Spec-Driven Development

- Source of truth: `docs/prd.md`, `docs/design.md` and `docs/tasks.md`.
- Never implement anything that is not in `docs/tasks.md`.
- If implementation reveals a spec problem, stop and propose a spec change before writing code.
- Never edit files in `data/` by hand; do all cleaning in code.

## Language

- All code, comments, docs, commit messages and the README are in English.
- The agent replies to customers in the customer's language, Brazilian Portuguese by default.

## Stack

- Python 3.12, managed with `uv`
- LangGraph for the agent graph
- LangChain `init_chat_model` for provider-agnostic LLMs (default: Google Gemini Flash)
- Chroma for policy RAG
- LangGraph SQLite checkpointer for conversation history
- Typer + Rich for the CLI
- ruff (lint and format), pytest

Use Context7 (if available) to check current LangGraph/LangChain APIs before using them.

## Commands

```bash
uv sync                    # install dependencies
uv run pytest              # run tests
uv run ruff check --fix    # lint
uv run ruff format         # format
```

App commands:

```bash
uv run emporio ingest                    # build the policy index (idempotent)
uv run emporio chat [--show-tools] [--session ID] [--store-today YYYY-MM-DD]
uv run emporio eval [--case ID ...]      # agent eval, writes var/eval-report.md
uv run emporio export --session ID       # Markdown transcript
uv run emporio sessions                  # list saved sessions
uv run pytest -m "not llm"               # unit tests only (plain pytest also runs live-model tests when a key is set)
```

## Code style

- Type hints everywhere.
- Data tools are small, pure functions.
- Pydantic models for tool inputs and outputs.
- No global state.
- Configuration through pydantic-settings and `.env`.

## Rules

- Never hardcode API keys; read them from the environment (`.env`, with `.env.example` tracked).
- Never let the LLM invent store facts: products, prices, stock, orders and policies come from tools only.
- Every tool has unit tests that do not call an LLM.
- Tests that need an LLM are marked and skipped when no API key is set.

## Definition of done (per task)

1. `uv run pytest` passes.
2. `uv run ruff check` is clean.
3. The task's checkbox in `docs/tasks.md` is ticked.
4. Specs are updated if the implementation changed anything.
5. One conventional commit (e.g. `feat: add order lookup tool`).
