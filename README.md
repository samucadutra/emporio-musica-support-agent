# Empório da Música support agent

## 1. What this is

A Python customer-support agent for a fictional musical instrument store in Campo Grande/MS. The agent, **Lia**, answers in Brazilian Portuguese (or the customer's language) using two sources only: the store's CSV data and its policy PDF.
Products, prices, stock, orders and rules come from tools, never from the model's memory. When Lia can't answer, she hands the case to a person.
It is a take-home prototype for an AI Engineer role ([challenge](docs/challenge.pdf)), built spec-first from [`docs/prd.md`](docs/prd.md), [`docs/design.md`](docs/design.md) and [`docs/tasks.md`](docs/tasks.md).

Excerpt from [`examples/03-preco-promocao-multiturno.md`](examples/03-preco-promocao-multiturno.md) (model: `gemini-3.1-flash-lite-preview`):

```text
Cliente: Quanto custa o Takamine GD20?
  tool: get_product_details {"name": "Takamine GD20"} → 95 · disponível · R$ 2.199,00 · pix R$ 2.089,05
Lia: O Takamine GD20 Dreadnought Natural custa R$ 2.199,00.
     Se preferir pagar via PIX, ele sai por R$ 2.089,05. Também podemos parcelar em até 12x
     de R$ 183,25. Ele está disponível em estoque!
```

What Lia can do: search the catalogue and quote price, promotion, PIX price and installments; check order status (only after the customer gives the order number **and** the email or phone of that order); give store address and hours; answer policy questions with the section cited; apply a policy to an order ("can I return order 7?"); open a handoff ticket for complaints, cancellations and returns.

## 2. Quickstart

Prerequisites: Python 3.12 and [`uv`](https://docs.astral.sh/uv/). About 220 MB of disk for the local embedding model, downloaded on first use.

```bash
uv sync
```

Create `.env` and add a key:

```bash
cp .env.example .env
```

The default model is Google Gemini. To get a free key, sign in at <https://aistudio.google.com/apikey>, create an API key, and paste it as `GOOGLE_API_KEY=...` in `.env`. The free tier allows only about 20 requests per day per model (see [Evaluation](#8-evaluation)).

Build the policy index (idempotent; downloads the embedding model on first run):

```bash
uv run emporio ingest
```

Chat with Lia (`chat` also builds the index if it is missing):

```bash
uv run emporio chat
```

Useful flags: `--show-tools` prints each tool call (emails and phones masked), `--session ID` resumes a session, `--store-today 2026-03-23` fixes the reference date for return windows. In the chat: `/sair`, `/nova`, `/exportar`, `/ajuda`.

Run the agent eval (needs the API key, see [Evaluation](#8-evaluation)):

```bash
uv run emporio eval
```

Other commands:

```bash
uv run emporio sessions                       # list saved sessions
uv run emporio export --session ID            # Markdown transcript
uv run pytest -m "not llm"                    # unit tests, no key needed
```

## 3. Switching LLM providers

`LLM_MODEL` is a LangChain `provider:model` string (via `init_chat_model`). Set it and the matching key in `.env`; non-default providers need an extra.

| Provider | `.env` | Install |
|---|---|---|
| Google Gemini (default) | `LLM_MODEL=google_genai:gemini-3.8-flash`<br>`GOOGLE_API_KEY=...` | included |
| OpenAI | `LLM_MODEL=openai:gpt-4.1-mini`<br>`OPENAI_API_KEY=...` | `uv sync --extra openai` |
| Anthropic | `LLM_MODEL=anthropic:claude-haiku-4-5`<br>`ANTHROPIC_API_KEY=...` | `uv sync --extra anthropic` |
| Ollama (local) | `LLM_MODEL=ollama:qwen3:8b`<br>`OLLAMA_BASE_URL=http://localhost:11434` | `uv sync --extra ollama` |

Only Gemini has been run end to end in this project. The other three are wired and unit-tested with fakes, but I did not run the eval against them. The Ollama model must support tool calling.

Embeddings are local and independent of the provider (`EMBEDDING_MODEL`); changing the model rebuilds the index.

## 4. Architecture

```mermaid
flowchart LR
    user([Customer]) --> cli["Typer + Rich CLI<br/>chat · ingest · eval · export · sessions"]
    cli -->|"thread_id + context"| agent
    subgraph graph["LangGraph StateGraph"]
        agent["agent node<br/>system prompt + bound tools"] -->|tool_calls| toolnode["ToolNode"]
        toolnode -->|ToolMessages| agent
    end
    agent -->|"init_chat_model"| llm[("LLM provider<br/>Gemini · OpenAI · Anthropic · Ollama")]
    graph <-->|checkpoints| ckpt[("SQLite<br/>var/agent.db")]
    toolnode --> catalog["search_products<br/>get_product_details<br/>list_categories"]
    toolnode --> orders["get_order_status"]
    toolnode --> storeinfo["get_store_info"]
    toolnode --> policies["search_policies"]
    toolnode --> handoff["request_human_handoff"]
    catalog --> repo[("Repository<br/>cleaned CSVs, in memory")]
    orders --> repo
    storeinfo --> facts["Store facts + clock"]
    policies --> chroma[("Chroma<br/>var/chroma")]
    chroma --- emb["fastembed (local)"]
    handoff --> hlog[("var/handoffs.jsonl")]
    cli -->|ingest| rag["PDF → heading chunks → embeddings"]
    rag --> chroma
```

Walkthrough of "Me arrependi, posso devolver o pedido 7?":

1. The CLI sends the message to the graph with `thread_id=<session>`; the SQLite checkpointer restores earlier turns.
2. The agent node builds the system prompt (rules plus the reference date) and calls the model. No email or phone yet, so the model asks for one and the turn ends.
3. The customer gives the email. The model calls `get_order_status(order_id=7, email=…)` and `search_policies(...)`; `ToolNode` runs them.
4. The order tool verifies the contact and returns the order with computed return-window flags. The policy tool returns the matching chunks (§4.1, §4.2, …).
5. The model answers from those results: window open or closed, the conditions, the section cited, and an offer to open a handoff, since Lia never executes returns.

## 5. Technical decisions

Full table with costs in [`docs/design.md`](docs/design.md) §15.

| Area | Chosen | Alternatives considered | Trade-off |
|---|---|---|---|
| Framework | Explicit LangGraph `StateGraph` (agent ⇄ `ToolNode`) | `create_agent`; hand-written loop over SDKs; router/classifier graph | Every step (prompt, retry, tool run, loop limit) is visible and testable, and the checkpointer comes built in. More code than `create_agent`; routing quality depends on the model, not a fixed classifier. |
| LLM | Gemini Flash via `init_chat_model` | GPT-4.1-mini, Claude Haiku, Ollama | Free tier, fast, good tool calling and Portuguese; switching is an env change. Free-tier quota is tight (see Limitations). |
| Data access | Typed read-only tools over in-memory data | Text-to-SQL agent; pandas agent; data in the prompt | Verification and privacy are enforced in code ("same customer only"); prices, PIX, installments and window dates are computed by the tools so the model does no arithmetic. Every new question type needs a tool. |
| Retrieval: chunking | One chunk per numbered heading of the PDF (26 chunks, no overlap), outline validated at ingest | Fixed-size 500–1000 chars with overlap; semantic chunking | Each chunk is one rule with its section number to cite; a changed PDF fails loudly instead of being mis-chunked. Tied to this document's outline. |
| Retrieval: embeddings | Local fastembed, `paraphrase-multilingual-MiniLM-L12-v2` (ONNX) | Gemini embeddings; sentence-transformers with torch; OpenAI embeddings | No key or quota, deterministic retrieval tests, no torch. Lower quality than large API models (offset by small, well-titled chunks); one-time ~220 MB download. |
| Retrieval: store | Chroma, persistent, with a manifest (model, PDF hash, chunker version) | FAISS; numpy; sqlite-vec | In the stack, persistent, metadata built in; stale index is rebuilt, never queried. Heavy for 26 vectors. |
| Policies | RAG behind a `search_policies` tool | Whole policy in the prompt (~3K tokens); hybrid BM25 + vector | Makes "consult policy" an explicit, testable decision with citations. A section could be missed, which full-context would not; retrieval tests cover known questions. Full context is the fallback. |
| Prompt | Short English prompt grouped by job (grounding, tool routing, verification, answering, handoff, scope, security); no store facts except the date; tool docstrings explain how to read each result; Portuguese replies | Prompt in Portuguese; facts in the prompt | Matches the code-language rule and models follow English rules well. Some fixed phrases must be written in Portuguese inside it. |
| Persistence | LangGraph SQLite checkpointer, one thread per session | In-memory; JSON files; Postgres | Survives restarts, no setup. Single process; no cross-session customer memory (intentional, for privacy). |
| Interface | Typer + Rich CLI, plus an optional Streamlit page over the same graph | Streamlit or FastAPI only; notebook | Fast path to a reliable demo and transcripts; the challenge allows a CLI. Less approachable for non-technical users. |
| Handoff | Tool writing a local JSONL ticket log | SQLite table; email/WhatsApp; LangGraph `interrupt` | Simple and inspectable. No real notification reaches staff. |
| Evaluation | Deterministic YAML cases (expected tools, substrings, regexes) | LLM-as-judge; human review | Reproducible and cheap; misses paraphrases and tone. |

## 6. Data handling

All cleaning is done in code at load time; `data/` is never edited. The audit (18 issues) is in [`docs/data-inventory.md`](docs/data-inventory.md) §4; decisions D1–D11 are in §9.

- **Loading:** explicit table → file mapping (the CSV file names have prefixes and `Zone.Identifier` artifacts); products sorted by ID; `specs` parsed into a dict; empty strings become `None`; dates parsed; `payment_method` (`credit_12x`) split into method and installments.
- **Search:** accent- and case-insensitive keys (NFKD, strip combining marks, casefold); displayed text unchanged. "cedro" matches the typo "Cedr" in product 84.
- **Availability** is `active` and stock > 0. Otherwise: "temporariamente indisponível", "fora de catálogo" (discontinued) or "em breve". Listings show only buyable products; lookup by name returns any status with its label.
- **Promotions** have no dates, so one is current only when `is_active == 1` and the product is available. At most one per product, and the 5% PIX discount never stacks on it.
- **Products 135–144** have descriptions and specs that contradict their names (for example a "Music Man" described as a Fender). They are served with name, price, availability and status only. They stay in the catalogue because order 10 contains product 135.
- **Historical orders are reported as stored:** totals that don't match item prices (orders 3, 20), PIX orders charged at full price, and installments below the policy minimum are not "fixed".
- **Delivery** uses `estimated_delivery` and the tracking code from the data, not the policy's timings, even where they disagree (issue 18).
- **Contradictions in the policy** are resolved by decision: canonical email `contato@emporiodamusica.com.br`, phone (67) 3341-4444, WhatsApp (67) 3321-4500.
- **PDF:** extracted with pypdf, page headers and footers removed, chunked by heading.
- **Start-up validation** checks referential integrity, one current promotion per product, and that the canonical store facts and window lengths appear in the policy text. It fails loudly if the data changes shape.
- **Privacy:** the model sees only the verified order's fields and the customer's first name. Logs, the tool trace and the handoff log mask emails and phones. An unknown order and a wrong contact return the same generic answer.

## 7. Assumptions

The full list (A-01 to A-21) is in [`docs/prd.md`](docs/prd.md) §4. The ones that change behaviour most:

- **Reference date:** for `delivered` orders, `estimated_delivery` is the receipt date. "Today" for return windows comes from `STORE_TODAY` (falls back to the real date). The data's effective date is `2026-03-23`. Without it, every order is far outside every window. "Open now?" always uses the real clock in America/Campo_Grande.
- **No holiday calendar:** the agent states the policy and computes `open_now` from weekday and time only.
- **Cancellations, returns and exchanges are never executed.** Lia explains eligibility and hands off.
- **Order access** needs the order number plus an email or phone that matches that order. There is no listing by email (one email appears on two customers).
- **Installments:** minimum R$ 50 / 80 / 100 for 1–3x / 4–6x / 7–12x, maximum 12x.
- **Shipping** is quoted only for Campo Grande (free above R$ 500, else R$ 35); other cities get carrier ranges and a handoff.
- **Order exclusions** (§4.4 of the policy) can't be checked from the data, so Lia names them as conditions and never says an order is or isn't excluded.
- **Phone matching** is digits only; a leading `55` or `0` is dropped and the 11 remaining digits must match.
- The window for preference exchange (§4.3) counts from receipt like §4.1; the policy doesn't say.
- The persona name "Lia" is my UX choice, not from the store's material.

## 8. Evaluation

Unit tests need no key (435 pass at the time of writing):

```bash
uv run pytest -m "not llm"
```

The agent eval is 15 deterministic cases ([`evals/cases.yaml`](evals/cases.yaml)) from PRD §10. Each case checks expected and forbidden tool calls plus accent- and case-insensitive substrings or regexes on the reply. There is no LLM judge.

```bash
uv run emporio eval                       # all cases; table + var/eval-report.md; exit 1 on failure
uv run emporio eval --case order-8-late   # selected cases (repeat --case)
uv run pytest -m llm                      # same cases through pytest
```

Plain `uv run pytest` also runs the live cases when a key is set.

**Latest results** ([`docs/eval-results.md`](docs/eval-results.md)): 15/15 cases pass, but **not from one single run**. The original default model (`gemini-2.5-flash`) stopped being served to new keys, and the free tier allows about 20 requests per day per model while a full run needs about 40. I ran the cases in batches across several Flash models and reported it as a split run.

- One real behaviour fix came out of the eval: `prompt-injection-discount` quoted the real price but never refused. A prompt rule now makes the reply say plainly that it can't break its rules.
- Two case checks ("conferida", "encerrou") were too strict for correct replies. I widened them and checked them offline; those two cases were not re-run live with the final file.
- `return-order-7-outside-window` is unstable on a lite model (one run opened a handoff unprompted and omitted "garantia legal"). It was not run on a full Flash model.
- Latency over 20 successful turns on mixed, rate-limited models: p50 ≈ 4.7 s, p95 ≈ 16.9 s (target p95 ≤ 15 s, so slightly over; includes retries).

## 9. Example conversations

Recorded from the real CLI with `emporio export`. Each file lists the model and reference date used.

- [`01-violoes-ate-1000.md`](examples/01-violoes-ate-1000.md): catalogue search with a price cap; returns all 12 matching acoustic guitars.
- [`02-endereco-e-horario.md`](examples/02-endereco-e-horario.md): store address and Saturday hours, plus whether the store is open now.
- [`03-preco-promocao-multiturno.md`](examples/03-preco-promocao-multiturno.md): price, PIX price and installments, then a follow-up on a promoted product.
- [`04-devolucao-pedido-7.md`](examples/04-devolucao-pedido-7.md): return request for order 7 at two reference dates, with verification, order windows and policy citations.
- [`05-fora-de-escopo.md`](examples/05-fora-de-escopo.md): strings and saxophone; instruments only, no saxophone in stock, no invention.

## 10. Known limitations and what I would do with more time

- **Verification can be brute-forced** (order number plus guessed email or phone). A real system would use a one-time code.
- **Static snapshot:** CSVs are loaded once. Lia can't place, change or cancel orders, take payments or start returns.
- **No holiday calendar**, and shipping quotes only for Campo Grande.
- **Eval is a split run, not one clean run**, and it only covers Gemini models. With a billed key I would run the full eval on one model, then on one model per provider.
- **Substring checks** miss paraphrases and tone. Next step: an LLM judge for tone and grounding, kept next to the deterministic checks.
- **Small models are less reliable** at "explain the next open window" (see Evaluation).
- **No history trimming:** sessions are short. Long ones need trimming that keeps tool calls with their results.
- **LangSmith tracing is not masked.** If `LANGSMITH_TRACING=true`, traces include raw customer messages. Use it only with this synthetic data.
- **Handoff is a local file.** No real notification reaches staff.
- **Retrieval quality is tested on known questions only.** A larger labelled set would show where MiniLM misses.

## 11. How I used AI coding assistants

I built this with Claude Code, spec first. The log with per-phase detail is [`docs/ai-usage-log.md`](docs/ai-usage-log.md).

**Workflow**

1. [`CLAUDE.md`](CLAUDE.md) holds the rules the assistant must follow: stack, code style, "never implement anything that isn't in `docs/tasks.md`", "if the spec is wrong, stop and propose a change before coding", never edit `data/`, definition of done.
2. A data inventory first (`scripts/inspect_data.py`, read-only), then PRD → design → tasks (33 tasks, each with files, acceptance criteria, tests and a commit message). In plan mode the assistant drafted each document and asked questions; I answered them and reviewed the drafts.
3. Implementation was one task at a time, with a plan first, then tests and ruff, then my review of the diff and one conventional commit per task. I make the commits myself; the assistant does not run `git commit`.

**Decisions made by me** (recorded in the log): the persona name "Lia"; a handoff tool with a local log; sparing emoji; local fastembed embeddings; an explicit `StateGraph` rather than a prebuilt agent; Gemini Flash as the default model; the data-handling decisions D1–D11 after the assistant's recommendations.

**Where the assistant was wrong, and how it was caught**

- In self-review of the PRD it caught its own "show up to 10 results" rule, which would have cut the 12-item violões example, and an invented stock-quantity rule. Fixed before I reviewed.
- Ranking alternatives by price alone would not have suggested the 7-string 112 for discontinued product 113; the design now ranks by name features first. This surfaced while it checked the design against the data.
- Two eval checks were too strict for correct replies. I found that by reading the actual replies, not only the pass/fail table.
- A plain `pytest` began running live-model tests once a key was in `.env` and hung; the fix was the `llm` marker and `-m "not llm"`.
- Example recordings: three first takes were rejected and re-recorded (an unrequested handoff ticket, half of a question skipped, replies lost to quota).
- The exported header showed `STORE_TODAY: not set` for sessions recorded with `--store-today`, because `export` reads the environment. Fixed by documenting that `STORE_TODAY` must be set when exporting.
- The assistant said it needed a live key for T30 and did not tick the task without one. I treated that as the right behaviour, but the split-run result comes from that constraint.

> **TODO (author):** the log has no entries for T01–T27 yet. Before submitting, add from your own review notes what you changed by hand and what the assistant got wrong in those tasks. I did not write them because I don't have that information.

## 12. Project structure

```text
.
├── CLAUDE.md                  # rules for the AI assistant
├── data/                      # CSVs and policy PDF (never edited)
├── docs/                      # challenge, data-inventory, prd, design, tasks, eval-results, ai-usage-log
├── evals/cases.yaml           # 15 agent eval cases
├── examples/                  # recorded conversations
├── scripts/inspect_data.py    # one-off read-only data inspection
├── src/emporio_musica_support_agent/
│   ├── cli.py, app.py         # Typer commands and dependency wiring
│   ├── config.py              # pydantic-settings
│   ├── llm.py                 # init_chat_model + retries
│   ├── agent/                 # graph.py, prompts.py, context.py
│   ├── tools/                 # catalog, orders, policies, store, handoff, registry, schemas
│   ├── data/                  # loader, cleaning, models, repository, validation
│   ├── domain/                # pricing, store hours, return/warranty windows
│   ├── rag/                   # PDF extract, chunking, Chroma index
│   ├── evals/                 # case schema, harness, report
│   ├── ui/                    # optional Streamlit chat
│   └── sessions.py, export.py, clock.py, privacy.py, logging_setup.py, text.py
├── tests/                     # unit/, retrieval/, agent/ (live, marked llm)
└── var/                       # generated state (gitignored): sessions, index, model cache, logs, tickets
```

Optional web chat over the same agent:

```bash
uv sync --extra ui
uv run streamlit run src/emporio_musica_support_agent/ui/streamlit_app.py
```
