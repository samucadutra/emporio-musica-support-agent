# Empório da Música support agent

A Python customer-support agent for a fictional musical instrument store in Campo Grande/MS. The agent is **Lia**. She answers in Brazilian Portuguese (or the customer's language) using only two sources: the store's data (`data/*.csv`) and its policy manual (`data/políticas_da_loja.pdf`). She never invents products, prices, stock, orders or rules, and she hands the case to a person when she can't answer.

This is a take-home prototype for an AI Engineer role (challenge statement: [`docs/challenge.pdf`](docs/challenge.pdf)). It was built spec-first: [`docs/prd.md`](docs/prd.md), [`docs/design.md`](docs/design.md) and [`docs/tasks.md`](docs/tasks.md) are the source of truth.

## Overview

What Lia can do:

- **Catalogue:** search by category, brand, name or price range; price, promotion, PIX price, installments and availability of one product; alternatives when a product is unavailable.
- **Orders:** status, items, tracking and lateness, only after the customer gives the order number **and** the email or phone of that order.
- **Store info:** address, phone, WhatsApp, email, opening hours and whether the store is open right now.
- **Policies:** exchanges, returns, warranty, payment, shipping, privacy, answered from the policy text with the section cited (RAG).
- **Policy applied to an order:** "can I return order 7?" combines the order's computed return windows with the policy conditions.
- **Handoff:** complaints, cancellations, returns and anything she can't answer become a ticket in a local log, with the team's contacts and hours.

How it works:

```
Typer + Rich CLI ─▶ LangGraph agent ⇄ ToolNode ─▶ 7 typed tools ─▶ cleaned CSV snapshot (in memory)
                         │                                       ├▶ Chroma index of the policy PDF (local embeddings)
                         │                                       └▶ store facts + clock, handoff log (JSONL)
                         └▶ SQLite checkpointer (one thread per session)
```

Tools: `search_products`, `get_product_details`, `list_categories`, `get_order_status`, `search_policies`, `get_store_info`, `request_human_handoff`.

Example conversations recorded from the real CLI are in [`examples/`](examples/).

## Setup

Requirements: Python 3.12 and [`uv`](https://docs.astral.sh/uv/). From a fresh clone:

```bash
uv sync
```

```bash
cp .env.example .env   # then set GOOGLE_API_KEY in .env
```

```bash
uv run emporio ingest  # builds the policy index; downloads a ~220 MB embedding model once
```

```bash
uv run emporio chat
```

`chat` also builds the policy index on its own if it is missing, so `ingest` is optional in practice; it stays the documented step because it is idempotent and shows what was indexed.

## Configuration

All settings come from `.env` or environment variables (see [`.env.example`](.env.example) and [`docs/design.md`](docs/design.md) §3).

**Model provider.** `LLM_MODEL` is a LangChain `provider:model` string. The default is `google_genai:gemini-3.8-flash` with `GOOGLE_API_KEY`. Other providers need only the key and an extra:

| Provider | `LLM_MODEL` example | Install | Key |
|---|---|---|---|
| Google Gemini (default) | `google_genai:gemini-3.8-flash` | included | `GOOGLE_API_KEY` |
| OpenAI | `openai:gpt-4.1-mini` | `uv sync --extra openai` | `OPENAI_API_KEY` |
| Anthropic | `anthropic:claude-haiku-4-5` | `uv sync --extra anthropic` | `ANTHROPIC_API_KEY` |
| Ollama (local) | `ollama:qwen3:8b` | `uv sync --extra ollama` | `OLLAMA_BASE_URL` |

Gemini's free tier allows only about 20 requests per day per model, which a full eval run exceeds. Use a billed key, or spread the work across models (see Evaluation).

**Reference date (`STORE_TODAY`).** The data is a snapshot, so "today" for return windows and late deliveries can be fixed with `STORE_TODAY=2026-03-23` (the data's effective date) or per run with `emporio chat --store-today 2026-03-23`. Unset, the real date is used. It never affects "is the store open now?", which always uses the real clock in America/Campo_Grande. `emporio export` reads `STORE_TODAY` from the environment for the transcript header, so set it there when you export a session recorded with `--store-today`.

**Order verification (phone and email matching).**
- Email: compared after trimming spaces and ignoring case.
- Phone: digits only; a leading `55` (13 digits) or `0` (12 digits) is dropped, and the remaining 11 digits (area code + number) must be equal. A number without the area code does not match.
- If both are given, both must match. An unknown order and a wrong contact return the same generic answer, so the agent never reveals which order numbers exist.

**LangSmith (optional).** Setting `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env` enables tracing. **Warning:** traces contain raw customer messages and tool outputs, including emails and phones typed by the customer. Use it only with the synthetic data in this repository. The app's own logs and `--show-tools` trace mask emails and phones; LangSmith traces do not.

## Usage

```bash
uv run emporio chat [--session ID] [--new] [--show-tools] [--store-today YYYY-MM-DD] [--verbose]
uv run emporio ingest [--force]
uv run emporio eval [--cases PATH] [--case ID ...] [--report PATH]
uv run emporio export --session ID [--out PATH] [--title TEXT] [--mask-user]
uv run emporio sessions
```

- `chat` starts a new session and prints its ID; `--session ID` resumes it, replaying the last three exchanges. `--show-tools` prints each tool call (arguments masked) and a one-line result summary.
- In the chat: `/sair` or `/exit`, `/nova` or `/new`, `/exportar [arquivo]` or `/export [file]`, `/ajuda` or `/help`. Ctrl-C cancels a reply, Ctrl-D exits.
- `ingest` builds or refreshes the policy index and does nothing when it is up to date.
- `eval` runs the agent eval (below) and writes a Markdown report.
- `export` writes a saved session as a Markdown transcript. Customer text is exported as typed (the data is synthetic); `--mask-user` masks it too.
- `sessions` lists saved sessions with last update and message count.
- Generated state lives in `var/` (gitignored): conversations (`agent.db`), the policy index, the model cache, handoff tickets (`handoffs.jsonl`) and JSON logs.

Optional web chat over the same agent: see [Streamlit UI](#streamlit-ui-optional).

## Design decisions

The full reasoning, with alternatives, is in [`docs/design.md`](docs/design.md) §15. The main choices:

- **Explicit LangGraph `StateGraph` (agent ⇄ `ToolNode`)** instead of a prebuilt agent. Every step (prompt, retries, tool execution, loop limit) is visible and testable, and the SQLite checkpointer gives persistent sessions.
- **Typed tools over in-memory data**, not a SQL or pandas agent. Verification and privacy are enforced in code, and prices, installments, PIX and return-window dates are computed by the tools so the model never does arithmetic. Tool outputs carry pre-formatted values (`R$ 2.199,00`) that the model copies.
- **RAG for policies** behind a `search_policies` tool. The PDF is chunked by its own numbered headings (26 chunks, no overlap), so every chunk is one rule and the section number to cite is in its metadata. The outline is validated at ingest, so a changed PDF fails loudly instead of being mis-chunked.
- **Local embeddings** (fastembed, multilingual MiniLM, ONNX): no key or quota, deterministic retrieval tests. The index records a manifest (model, PDF hash, chunker version), so ingest is idempotent and a stale index is rebuilt, never queried.
- **Provider-agnostic model** through `init_chat_model`; switching provider is a `.env` change. Rate limits and 5xx errors are retried with backoff.
- **Prompt strategy.** A short English prompt grouped by job (grounding, tool routing, verification, answering, handoff, scope, security). It carries no store facts, only the reference date. Tool docstrings tell the model how to read each result. A "scope" rule (instruments only, never accessories) is the single fact the model knows without a tool.
- **Data is cleaned in code, never by hand.** Accent- and case-insensitive search, products 135–144 with unreliable descriptions shown without descriptions, availability labels, one current promotion per product, and historical order totals reported as stored. Start-up validation fails loudly if the data changes shape.
- **Privacy.** The model sees only the verified order's fields and the customer's first name. Logs, the tool trace and the handoff log mask emails and phones.

## Assumptions

Ambiguities in the challenge and the data were resolved explicitly; the full list (A-01 to A-21) is in [`docs/prd.md`](docs/prd.md) §4, backed by the data audit in [`docs/data-inventory.md`](docs/data-inventory.md). Examples: the delivery estimate of a delivered order is its receipt date; a promotion is current only while the product is in stock and the PIX discount never stacks on it; installment minimums are R$ 50 / 80 / 100 for 1–3x / 4–6x / 7–12x; shipping is quoted only for the Campo Grande rule; the agent never executes cancellations or returns, it explains eligibility and hands off.

## Evaluation

Unit tests need no LLM or key:

```bash
uv run pytest -m "not llm"
```

Plain `uv run pytest` also runs the 15 live-model eval cases when a key for `LLM_MODEL` is set (they skip cleanly otherwise). `-m "not embeddings"` skips tests that need the local embedding model.

The agent eval is 15 deterministic cases from PRD §10 (`evals/cases.yaml`): expected and forbidden tool calls, plus accent- and case-insensitive substrings and regexes on the reply. There is no LLM judge.

```bash
uv run emporio eval                      # all cases; table + var/eval-report.md; exit 1 on any failure
uv run emporio eval --case order-8-late  # selected cases
uv run pytest -m llm                     # the same cases through pytest
```

Latest results ([`docs/eval-results.md`](docs/eval-results.md)): **15/15 cases pass**, but from a run split across several Gemini Flash models because of the free-tier daily quota, not one single run. A prompt rule was added after the injection case failed. Turn latency over 20 successful turns was p50 ≈ 4.7 s and p95 ≈ 16.9 s on mixed, rate-limited models. One case (`return-order-7-outside-window`) was unstable on a lite model.

## Limitations and future work

- **Verification can be brute-forced** (order number plus a guessed email or phone). A real system would use an OTP. This is accepted for a prototype.
- **No holiday calendar:** the agent says the store is closed on holidays but cannot know which days are holidays.
- **Static snapshot:** the CSVs are loaded once; the agent cannot place, change or cancel orders, take payments or start returns.
- **Shipping quotes** exist only for the Campo Grande rule; other cities get carrier time ranges and a handoff.
- **No history trimming:** sessions are short; long sessions would need trimming that keeps tool calls with their results.
- **Substring-based eval** misses paraphrases and tone; an LLM judge would be the next step.
- **Free-tier quota** limits how often the full eval can run; the headline result is a split run, not a single clean one.
- **LangSmith traces are not masked**, and the order-7 "outside the window" case is less reliable on small models.
- The persona name "Lia" is a UX choice, not from the store's material.

## AI-assisted workflow

The project was built with Claude Code, spec first: data inventory, PRD, design and a task list were written and reviewed before any code, then each task was planned and implemented from the task list, with conventional commit messages. The assistant never committed; the commits are the author's. A running log of what was asked, what I changed by hand and what the assistant got wrong is in [`docs/ai-usage-log.md`](docs/ai-usage-log.md).

## Streamlit UI (optional)

A minimal web chat over the same graph, checkpointer and tools (no extra business logic):

```bash
uv sync --extra ui
uv run streamlit run src/emporio_musica_support_agent/ui/streamlit_app.py
```

The session ID is shown in the sidebar and kept in the URL (`?session=ID`), so reloading or opening the link resumes the conversation. A sidebar toggle shows the masked tool trace for each reply.
