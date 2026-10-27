# Implementation tasks

Status: draft for review · Date: 2026-10-27 · Implements [`prd.md`](prd.md) and [`design.md`](design.md).

How to use this file:
- Work top to bottom. Each task depends only on the tasks above it.
- Each task is one commit (30–90 min) and leaves `uv run pytest` green and `uv run ruff check` clean.
- Definition of done (CLAUDE.md): tests pass, ruff clean, the task's checkbox ticked here, specs updated if the implementation changed anything, one conventional commit.
- "Design §n" points to `design.md`; FR/NFR/A-nn point to `prd.md`.
- Before using a LangGraph or LangChain API, check the current docs (Context7).

---

### [x] T01 — Project scaffolding

- **Goal:** Runtime and dev dependencies, the `emporio` console script, pytest markers and ruff config, so every later task has a place to land.
- **Files:** `pyproject.toml`, `uv.lock`, `.gitignore`, `src/emporio_musica_support_agent/__init__.py`, `src/emporio_musica_support_agent/cli.py`, `tests/conftest.py`, `tests/unit/test_smoke.py`
- **FRs:** FR-14 (CLI entry point) (NFR-09)
- **Acceptance criteria:**
  - [x] Runtime deps from design §2 added (`pypdf` moved from dev to runtime); extras `openai`, `anthropic`, `ollama`; `pandas` stays dev only.
  - [x] Console script `emporio = "emporio_musica_support_agent.cli:app"` replaces the template `main`; `uv run emporio --help` prints a Typer help screen.
  - [x] Pytest markers `llm` and `embeddings` registered; ruff configured (line length, import sorting, target py312).
  - [x] `.gitignore` contains `var/`.
- **Tests:** `test_smoke.py`: package imports; Typer `CliRunner` runs `--help` with exit code 0.
- **Commit:** `build: add dependencies, emporio CLI entry point and test config`

### [x] T02 — Settings and `.env.example`

- **Goal:** All configuration through pydantic-settings (design §3).
- **Files:** `src/.../config.py`, `.env.example`, `tests/unit/test_config.py`
- **FRs:** — (NFR-05, NFR-07, A-02)
- **Acceptance criteria:**
  - [x] `Settings` has every field in design §3 with the listed defaults; API keys are `SecretStr | None`; `store_today: date | None`.
  - [x] `Settings.export_provider_env()` copies set keys and `LANGSMITH_*` entries from `.env` into `os.environ` without overwriting existing values.
  - [x] `.env.example` matches design §3 verbatim; no real key anywhere.
- **Tests:** defaults; `.env` parsing from a temp file; `STORE_TODAY` parsed as `date`; `export_provider_env` doesn't overwrite an existing env var.
- **Commit:** `feat: add settings and env example`

### [x] T03 — Text helpers and clock

- **Goal:** Search-key folding, BRL formatting, money rounding, and an injectable clock.
- **Files:** `src/.../text.py`, `src/.../clock.py`, `tests/unit/test_text.py`, `tests/unit/test_clock.py`
- **FRs:** FR-01 (accent-insensitive match), FR-05 (clock)
- **Acceptance criteria:**
  - [x] `fold()` does NFKD, strips combining marks, casefolds, collapses whitespace, treats `-` and `/` as spaces.
  - [x] `format_brl(Decimal("2199")) == "R$ 2.199,00"`; `round_money` uses `ROUND_HALF_UP` to 2 places.
  - [x] `Clock` protocol with `now(tz)`; `SystemClock`, `FixedClock`.
- **Tests:** `fold("VIOLÃO") == "violao"`; `fold("Cedr-Natural")`; formatting of 0, 159.9, 2089.05, 19567; half-up rounding; `FixedClock` returns a tz-aware datetime in the requested zone.
- **Commit:** `feat: add text folding, BRL formatting and clock`

### [x] T04 — Privacy helpers

- **Goal:** Contact normalization for verification and PII masking for logs, traces and handoffs (design §6.4, §6.7).
- **Files:** `src/.../privacy.py`, `tests/unit/test_privacy.py`
- **FRs:** FR-04, FR-13 (NFR-02)
- **Acceptance criteria:**
  - [x] `emails_match()` (strip, remove inner whitespace, casefold) and `phones_match()` (digits only, strip leading `55`/`0` per design §6.4, 11 digits required).
  - [x] `mask_email("leticia.rocha@jmail.com") == "le***@jmail.com"`; `mask_phone` keeps only the last digits.
  - [x] `mask_pii(text)` masks every email and phone pattern except the store's own numbers and email.
- **Tests:** phone variants (`67997890123`, `+55 (67) 99789-0123`, `067...`) match; 9-digit number without DDD doesn't; email case/space variants; store WhatsApp/phone left unmasked; mixed text masked.
- **Commit:** `feat: add contact matching and PII masking`

### [x] T05 — Data models, loader and cleaning

- **Goal:** Load the six CSVs into validated Pydantic models with all cleaning rules applied in code (design §5.1–5.2).
- **Files:** `src/.../data/models.py`, `src/.../data/loader.py`, `src/.../data/cleaning.py`, `tests/conftest.py`, `tests/unit/test_cleaning.py`
- **FRs:** FR-03 (availability label), FR-09 (unreliable descriptions)
- **Acceptance criteria:**
  - [x] `TABLE_FILES` / `POLICY_FILE` explicit mapping; `Zone.Identifier` files never read; missing file raises `DataFileNotFoundError(table, path)`.
  - [x] `""` → `None`; ISO dates parsed; `specs` parsed to dict; `payment_method` split into method + installments with pt-BR label; products sorted by ID.
  - [x] `UNRELIABLE_DESCRIPTION_IDS = frozenset(range(135, 145))` with a comment citing issue #4 / D4; `Product.description_reliable` derived.
  - [x] Availability label per design §5.2 table.
  - [x] `data/` untouched (stdlib `csv`, no pandas).
- **Tests:** row counts (9/65/25/20/22/50); 145 after 144; `credit_12x` → (`credit`, 12, "cartão de crédito em 12x"); order 1 tracking present, order 13 tracking `None`; labels for 96, 113, 130, 136; 135 unreliable, 134 reliable; missing data dir raises `DataFileNotFoundError`. Session-scoped `data_dir` fixture in `conftest.py`.
- **Commit:** `feat: load and clean store CSV data`

### [x] T06 — Repository: indexes, search and name lookup

- **Goal:** In-memory `Repository` with the query API from design §5.4 (minus pricing and alternatives).
- **Files:** `src/.../data/repository.py`, `tests/conftest.py`, `tests/unit/test_repository.py`
- **FRs:** FR-01, FR-08, FR-09
- **Acceptance criteria:**
  - [x] `Repository.load(data_dir)`; `categories`, `resolve_category` (ID, name or `CATEGORY_ALIASES`), `get_product`, `get_order`, `get_order_items`, `get_customer`.
  - [x] `search_text` per design §5.3, description left out for unreliable IDs; stop words dropped; every token must be a substring.
  - [x] `search_products(...)` filters by query, category, brand (substring of folded name), price range, `only_available`; sorted by list price then name.
  - [x] `find_products_by_name` follows the 3-step lookup and returns match or candidates.
- **Tests:** `category_id=5, max_price=1000` → the 12 IDs in PRD §12 order; "violao ate 1000" via free text matches the same set; "cedro" matches 84; "fender" doesn't match 135; "saxofone" resolves to category 6 with no products; "Takamine GD20" → match 95; "yamaha" → several candidates; typo "takamine gd2O" → fuzzy candidates. Session-scoped `repo` fixture.
- **Commit:** `feat: add in-memory store repository with search`

### [x] T07 — Pricing: promotions, PIX and installments

- **Goal:** Pure pricing rules (design §6.2) and the repository's promotion queries.
- **Files:** `src/.../domain/pricing.py`, `src/.../data/repository.py`, `tests/unit/test_pricing.py`
- **FRs:** FR-02
- **Acceptance criteria:**
  - [x] `Repository.current_promotion` (is_active and product `disponível`, A-05) and `inactive_promotions`.
  - [x] `final_price`, `pix_price` (None when a promotion is current), `installment_options` (1..12 with tiers A-11), `max_installments` — all `Decimal`, half-up.
- **Tests:** 95: no current promotion, PIX 2089.05, 12x 183.25, inactive "Oferta Especial (12%)" listed; 121: final 439.20, no PIX; 81: max 6x of 99.98, 7x not allowed; at most one current promotion per product across the catalogue; a promotion on an out-of-stock product is not current (synthetic product).
- **Commit:** `feat: add pricing rules for promotions, PIX and installments`

### [x] T08 — Alternatives for unavailable products

- **Goal:** `Repository.alternatives_for` with feature-weighted ranking (design §5.4).
- **Files:** `src/.../data/repository.py`, `tests/unit/test_repository.py`
- **FRs:** FR-03
- **Acceptance criteria:**
  - [x] Same category, `disponível`, within ±60% price; ranked by `FEATURE_WEIGHTS` score then |price diff|; filled from outside the band if fewer than n.
  - [x] Never returns the product itself or an unavailable product.
- **Tests:** 113 → [110, 112, …]; 96 → starts with 91; result length ≤ 3; all results `disponível`.
- **Commit:** `feat: suggest alternatives for unavailable products`

### [ ] T09 — Catalog tools: `search_products` and `list_categories`

- **Goal:** Shared tool schemas and the first two pure tool functions (design §6, §6.1, §6.3).
- **Files:** `src/.../tools/__init__.py`, `src/.../tools/schemas.py`, `src/.../tools/catalog.py`, `tests/unit/test_tools_catalog.py`
- **FRs:** FR-01, FR-03, FR-08, FR-09
- **Acceptance criteria:**
  - [ ] `Money`, `PromotionInfo`, `ProductSummary`, `SearchProductsInput`, `ProductSearchResult`, `CategorySummary`, `CategoryListResult` as in design §6.
  - [ ] `search_products(repo, params)`: limit/truncation, `category_matched`, notes for unknown and empty categories, `closest_matches` when total is 0 and a name-like query was given.
  - [ ] `list_categories(repo)` returns all 9 categories with `available_count` (6–8 are 0).
  - [ ] Docstrings as in design §6.1 / §6.3.
- **Tests:** violões ≤ 1000 → 12 IDs in order, none of 96/113; `only_available=False` includes 96 and 113; `limit=5` → `truncated=True`, `total=12`; "saxofone" → total 0 with "category has no products"; unknown product name → `closest_matches`; promotion fields present for 121; `max_price < min_price` raises validation error; categories 6–8 count 0.
- **Commit:** `feat: add search_products and list_categories tools`

### [ ] T10 — Catalog tool: `get_product_details`

- **Goal:** One product's commercial facts with computed prices (design §6.2).
- **Files:** `src/.../tools/schemas.py`, `src/.../tools/catalog.py`, `tests/unit/test_tools_catalog.py`
- **FRs:** FR-02, FR-03, FR-09
- **Acceptance criteria:**
  - [ ] `ProductDetailsInput` (validator: ID or name), `Installments`, `InstallmentOption`, `ProductDetails`, `ProductDetailsResult`.
  - [ ] Description and specs `None` when unreliable; alternatives only when not `disponível`; candidates on ambiguous name.
- **Tests:** "Takamine GD20" → 95 with `pix_price.fmt == "R$ 2.089,05"`, 12x R$ 183,25, `inactive_promotions` non-empty; 121 → promotion set, `pix_price is None`; 81 → max 6x R$ 99,98; 113 → "fora de catálogo" with alternatives [110, 112, …]; 96 → "temporariamente indisponível"; 130 → "em breve"; 135 → no description/specs; "yamaha" → `found=False` with candidates; "violino stradivarius" → not found, no candidates; neither ID nor name → validation error.
- **Commit:** `feat: add get_product_details tool`

### [ ] T11 — Return and warranty windows

- **Goal:** Pure date-window logic (design §6.4 window rules).
- **Files:** `src/.../domain/windows.py`, `tests/unit/test_windows.py`
- **FRs:** FR-07 (A-01, A-02, A-14, A-15, A-19)
- **Acceptance criteria:**
  - [ ] `compute_windows(order, reference_date)` returns windows in FR-07 order, or `None` with the right note (not delivered, cancelled, order date after reference date).
  - [ ] Receipt = `estimated_delivery`; day `length_days` still open; `exclusions_to_check` and manufacturer-warranty note from §4.4 / §8.2.
  - [ ] `is_late(order, reference_date)` for shipped orders.
- **Tests:** order 7 at 2026-02-20 → arrependimento open (3 days); at 2026-03-23 → arrependimento closed (34), defeito closed (48), garantia legal open; boundary: day 7 open, day 8 closed; order 8 → no windows, `is_late` at 2026-03-23; cancelled order → note; order dated after reference → no windows.
- **Commit:** `feat: compute return and warranty windows`

### [ ] T12 — Order tool: `get_order_status`

- **Goal:** Verified order lookup that never leaks customer data (design §6.4).
- **Files:** `src/.../tools/schemas.py`, `src/.../tools/orders.py`, `tests/unit/test_tools_orders.py`
- **FRs:** FR-04, FR-07, FR-11
- **Acceptance criteria:**
  - [ ] Input validator demands email or phone, with the "ask the customer…" message.
  - [ ] Unknown order and contact mismatch return an identical `OrderStatusResult`; both contacts must match when both are given.
  - [ ] Verified output: first name, status label, items (names from the product table), total as stored, payment label, tracking, `is_late`, notes, windows; reference date = `store_today` or clock date.
- **Tests:** order 7 + `leticia.rocha@jmail.com` → verified, first name "Letícia"; phone `67997890123` verifies; wrong email for 7 equals result for order 9999 (`==` on dumps); email right + phone wrong → not verified; order 3 total 3450 (not recomputed); order 17 notes present; order 8 `is_late` with `STORE_TODAY=2026-03-23`; serializing every verified order contains no customer email or phone; missing contact → validation error.
- **Commit:** `feat: add verified get_order_status tool`

### [ ] T13 — Store facts and `get_store_info`

- **Goal:** Canonical store facts, hours, `open_now` and `next_opening` (design §6.6).
- **Files:** `src/.../domain/store.py`, `src/.../tools/schemas.py`, `src/.../tools/store.py`, `tests/unit/test_store.py`, `tests/unit/test_tools_store.py`
- **FRs:** FR-05, FR-13 (A-03, A-04, A-06)
- **Acceptance criteria:**
  - [ ] Store constants per A-06; hours Mon–Fri 09–18, Sat 09–13, Sun closed; `open ≤ t < close`.
  - [ ] `next_opening` scans up to 7 days; tool uses the clock only, never `STORE_TODAY`.
  - [ ] `holiday_note`, `hours_note`, `source_sections` filled.
- **Tests:** FixedClock Saturday 12:59 open with `closes_at` 13:00; Saturday 13:00 closed; Sunday closed → next Monday 09:00; weekday 08:59 closed → same day 09:00; `STORE_TODAY` set doesn't change `open_now`.
- **Commit:** `feat: add store facts and get_store_info tool`

### [ ] T14 — Handoff log and `request_human_handoff`

- **Goal:** Append-only JSONL handoff tickets with masked summaries (design §6.7).
- **Files:** `src/.../tools/schemas.py`, `src/.../tools/handoff.py`, `tests/unit/test_tools_handoff.py`
- **FRs:** FR-13 (NFR-02)
- **Acceptance criteria:**
  - [ ] `HandoffLog.append` writes `ticket_id, created_at, session_id, reason, summary, order_id`, creating parent dirs.
  - [ ] Ticket ID `EMP-<YYYYMMDD>-<4 hex>`, retried on collision.
  - [ ] Summary masked with `mask_pii`; complaint → `response_time_note`; `team_available_now` / `next_opening` from the store domain.
- **Tests:** ticket format; JSONL line fields; email/phone in summary are masked in the file; complaint note present, other reasons `None`; closed-store clock → `team_available_now=False` with `next_opening`; collision retry (patched token).
- **Commit:** `feat: add human handoff tool and log`

### [ ] T15 — Policy PDF extraction and fact checks

- **Goal:** Clean policy text from the PDF (design §7 extraction) and prove the coded facts match it.
- **Files:** `src/.../rag/__init__.py`, `src/.../rag/extract.py`, `tests/unit/test_policy_facts.py`
- **FRs:** FR-06 (A-21)
- **Acceptance criteria:**
  - [ ] Layout-mode extraction; headers, footers and trailer stripped; column runs → ` | `; bullets → `- `; page start offsets recorded.
  - [ ] D3 email fix applied.
- **Tests:** no "Página N" or header lines left; accented email gone, canonical email present; every canonical store fact from `domain/store.py` is in the text; A-21 numbers (7/30/90 dias, R$ 50/80/100, 12x, R$ 500, R$ 35, 5%) present; "Sábado | 09:00 às 13:00" row readable.
- **Commit:** `feat: extract clean text from the policy PDF`

### [ ] T16 — Start-up data validation

- **Goal:** Fail loudly if the data or policy changes shape (design §5.5).
- **Files:** `src/.../data/validation.py`, `tests/unit/test_validation.py`
- **FRs:** — (PRD §9, NFR-06)
- **Acceptance criteria:**
  - [ ] `validate(repo, policy_text)` checks FKs, ≤1 current promotion per product, enum values, store facts and A-21 numbers; raises `DataValidationError` listing every failure.
- **Tests:** real data passes; a mutated in-memory repo (orphan FK, two current promotions) and a policy text missing the address each produce a listed failure; multiple failures reported together.
- **Commit:** `feat: validate data and policy facts at start-up`

### [ ] T17 — Heading-aware policy chunking

- **Goal:** One chunk per numbered subsection, validated against `POLICY_OUTLINE` (design §7 chunking).
- **Files:** `src/.../rag/chunking.py`, `tests/unit/test_chunking.py`
- **FRs:** FR-06
- **Acceptance criteria:**
  - [ ] `POLICY_OUTLINE` with the 10 top-level and 18 numbered headings; missing heading raises.
  - [ ] Cover chunk `0`, intro chunks, 1,800-char split guard, metadata (`section_number`, `section_title`, `parent_title`, `page`, `part`, `chunker_version`), deterministic IDs, embedding text with title prefix; `CHUNKER_VERSION` constant.
- **Tests:** 26 chunks; every outline heading present; §7.2 "1. Saudação" doesn't start a chunk; §5.2 table and notes in one chunk; max chunk ≤ 1,800 chars; IDs stable across two runs; outline with a fake heading raises.
- **Commit:** `feat: chunk policy text by section headings`

### [ ] T18 — Local embeddings and `PolicyIndex`

- **Goal:** Persistent Chroma index with manifest-based idempotency (design §4, §7 index).
- **Files:** `src/.../llm.py` (`FastEmbedEmbeddings` only), `src/.../rag/index.py`, `tests/retrieval/test_policy_index.py`, `tests/unit/test_index_manifest.py`
- **FRs:** FR-06, FR-14 (ingest idempotency) (NFR-04, NFR-06)
- **Acceptance criteria:**
  - [ ] `FastEmbedEmbeddings` implements `embed_documents` / `embed_query`, cache in `models_cache_dir`.
  - [ ] `PolicyIndex.status()` → `missing` / `stale(reason)` / `ok`; `build(force)` is a no-op when up to date, writes `manifest.json` last; `search(query, k)` returns `PolicyChunk`s with `score = 1 − distance`.
- **Tests:** unit (fake `Embeddings`, no download): missing → build → ok; second build is a no-op; changed model name or PDF hash → stale; interrupted build (no manifest) → stale. `embeddings`-marked: real build in a temp dir returns 26 chunks.
- **Commit:** `feat: add local embeddings and persistent policy index`

### [ ] T19 — `search_policies` tool, retrieval tests and `emporio ingest`

- **Goal:** Expose policy retrieval as a tool and as the ingest command.
- **Files:** `src/.../tools/schemas.py`, `src/.../tools/policies.py`, `src/.../cli.py`, `tests/retrieval/test_policy_retrieval.py`, `tests/unit/test_cli.py`
- **FRs:** FR-06, FR-07, FR-14 (ingest)
- **Acceptance criteria:**
  - [ ] `SearchPoliciesInput`, `PolicyChunk`, `PolicySearchResult`; docstring per design §6.5.
  - [ ] `emporio ingest [--force]` prints chunk count and manifest, or "up to date".
- **Tests:** `embeddings`-marked hit@4 for the 12 questions in design §13; unit: tool returns chunks sorted by score with a fake index; `CliRunner` ingest twice with a fake index → second says "up to date".
- **Commit:** `feat: add search_policies tool and ingest command`

### [ ] T20 — Logging setup and dependency container

- **Goal:** PII-safe JSON logging and `build_deps` wiring with no globals (design §2 rules, §12).
- **Files:** `src/.../logging_setup.py`, `src/.../app.py`, `tests/unit/test_logging.py`, `tests/unit/test_app.py`
- **FRs:** — (NFR-02, NFR-08)
- **Acceptance criteria:**
  - [ ] `configure(settings, verbose)`: JSON-lines file handler, Rich console handler, `PIIMaskingFilter` on every handler (message and string `extra` fields).
  - [ ] `Deps` frozen dataclass (settings, repo, policy_index, handoff_log, clock); `build_deps(settings, clock=None)` creates `var/` dirs and loads everything once.
- **Tests:** a log record with an email in the message and in `extra` is masked in the file; `build_deps` with a temp `var_dir` returns a `Deps` whose repo has 65 products; passing a `FixedClock` is kept.
- **Commit:** `feat: add PII-safe logging and dependency wiring`

### [ ] T21 — Tool registry

- **Goal:** Wrap the pure tools as LangChain tools with logging and summaries (design §6 conventions).
- **Files:** `src/.../agent/__init__.py`, `src/.../agent/context.py`, `src/.../tools/registry.py`, `src/.../tools/schemas.py` (`summarize()` per output), `tests/unit/test_registry.py`
- **FRs:** FR-09, FR-13 (session_id from runtime), FR-14 (summaries for `--show-tools`) (NFR-08)
- **Acceptance criteria:**
  - [ ] `build_tools(deps)` returns the 7 tools with the design names, docstrings and `args_schema`.
  - [ ] Each wrapper times the call, logs `tool_call` (masked args, latency, size, summary, ok) and returns `model_dump_json(exclude_none=True)`.
  - [ ] `request_human_handoff` reads `session_id` from `ToolRuntime[AgentContext]`; the model-facing schema has no `session_id`/`runtime`.
  - [ ] `AgentContext` frozen dataclass.
- **Tests:** 7 tool names; each schema matches its Input model; invoking `search_products` returns JSON with 12 items; handoff schema hides runtime; a log record is emitted with masked email for `get_order_status`; each `summarize()` produces one line.
- **Commit:** `feat: register tools as LangChain tools with logging`

### [ ] T22 — Chat model factory and retry policy

- **Goal:** Provider-agnostic model creation and retries (design §4, §14).
- **Files:** `src/.../llm.py`, `tests/unit/test_llm.py`
- **FRs:** — (NFR-04, NFR-05)
- **Acceptance criteria:**
  - [ ] `build_chat_model(settings)` via `init_chat_model`; missing package → "run `uv sync --extra <provider>`".
  - [ ] `required_api_key(llm_model)` and `check_api_key(settings)` (Ollama needs none).
  - [ ] `is_retryable(exc)` and `invoke_with_retry(model, messages, settings)` with tenacity and `llm_retry` log events.
- **Tests:** provider → key mapping; missing key raises with variable name; `is_retryable` for fake exceptions with `status_code` 429/503, a `ResourceExhausted` class name, and a 401 (not retryable); `invoke_with_retry` retries a fake model that fails twice with 429 then succeeds (wait patched to 0); unknown provider package error message.
- **Commit:** `feat: add provider-agnostic chat model with retries`

### [ ] T23 — System prompt

- **Goal:** The Lia system prompt with the current-context block (design §9).
- **Files:** `src/.../agent/prompts.py`, `tests/unit/test_prompts.py`
- **FRs:** FR-04, FR-06, FR-07, FR-08, FR-09, FR-10, FR-11, FR-13 (prompt rules) (NFR-01)
- **Acceptance criteria:**
  - [ ] `SYSTEM_PROMPT` verbatim from design §9; `PROMPT_VERSION` constant.
  - [ ] `build_system_prompt(settings, clock)` fills reference date, pt-BR weekday and the simulated note only when `STORE_TODAY` is set.
  - [ ] No store facts beyond the scope rule (no prices, address, phone in the template).
- **Tests:** with `STORE_TODAY=2026-03-23` → "2026-03-23 (segunda-feira)" and simulated note; without it → FixedClock date in America/Campo_Grande and no note; template contains none of the canonical address/phone strings.
- **Commit:** `feat: add Lia system prompt`

### [ ] T24 — Agent graph

- **Goal:** Explicit `StateGraph` agent ⇄ `ToolNode` with checkpointing (design §8).
- **Files:** `src/.../agent/graph.py`, `tests/fakes.py` (scripted fake chat model), `tests/unit/test_graph_wiring.py`
- **FRs:** FR-07, FR-09, FR-11, FR-12
- **Acceptance criteria:**
  - [ ] `build_graph(deps, checkpointer, model=None)`; the system prompt is prepended per call and not stored in state.
  - [ ] `ToolNode(handle_tool_errors=True)`; `run_config(session_id, settings)` sets `thread_id` and `recursion_limit = 2 * max_tool_rounds + 1`.
  - [ ] `run_turn(graph, session_id, text)` returns the reply or the fixed fallback on `GraphRecursionError`; logs `turn_start` / `turn_end` / `llm_call`.
- **Tests (fake model, no LLM):** tool call → ToolMessage → final answer; two parallel tool calls both executed; a tool raising returns an error ToolMessage; endless tool calls → fallback reply; checkpoint resume on a temp `SqliteSaver` file across two graph instances; state never contains a `SystemMessage`.
- **Commit:** `feat: build LangGraph agent with tool loop and checkpointing`

### [ ] T25 — CLI `chat` with sessions

- **Goal:** Interactive Rich chat with new and resumed sessions (design §10, §11).
- **Files:** `src/.../cli.py`, `src/.../sessions.py` (session ID, checkpointer helpers), `tests/unit/test_cli.py`
- **FRs:** FR-12, FR-14 (chat) (NFR-06)
- **Acceptance criteria:**
  - [ ] Start-up: `export_provider_env`, logging, API key check (exit 2), `build_deps`, `validate`, index auto-build with notice.
  - [ ] `chat [--session ID] [--new] [--store-today] [--verbose]`: header panel, new session ID printed, `--session` resumes and shows the last 3 exchanges, unknown ID is an error.
  - [ ] Spinner "Lia está digitando…", replies as Markdown panels; `/sair`, `/exit`, `/nova`, `/new`, `/ajuda`, `/help`; Ctrl-C cancels a turn, Ctrl-D exits.
  - [ ] Retry-exhausted and other LLM errors show the design §14 messages.
- **Tests:** session ID format; `CliRunner` with a fake model via a monkeypatched factory: one exchange then `/sair`; resume prints prior turns; unknown session exits non-zero; missing key exits 2 with the variable name.
- **Commit:** `feat: add interactive chat command with persistent sessions`

### [ ] T26 — `--show-tools` trace and `sessions` command

- **Goal:** Visible, masked tool trace and session listing.
- **Files:** `src/.../cli.py`, `src/.../sessions.py`, `tests/unit/test_cli.py`
- **FRs:** FR-12 (list), FR-14 (`--show-tools`, sessions)
- **Acceptance criteria:**
  - [ ] With `--show-tools`, `graph.stream(stream_mode="updates")` prints each tool call with masked args and its one-line summary.
  - [ ] `emporio sessions` lists thread IDs with last update time and message count.
- **Tests:** fake-model chat with `--show-tools` prints `get_order_status` with `le***@jmail.com` and never the raw email; `sessions` lists two sessions created in a temp DB.
- **Commit:** `feat: add tool trace and sessions listing to the CLI`

### [ ] T27 — Transcript export

- **Goal:** Markdown transcripts for examples (design §11).
- **Files:** `src/.../export.py`, `src/.../cli.py`, `tests/unit/test_export.py`
- **FRs:** FR-14 (export, `/export`)
- **Acceptance criteria:**
  - [ ] `emporio export --session ID [--out] [--title] [--mask-user]` and in-chat `/exportar` / `/export`.
  - [ ] Header with model, `STORE_TODAY`, session and export time; `<details>` tool blocks with masked args and summaries; customer text as typed unless `--mask-user`.
- **Tests:** export a fake-model session → file contains title, header lines, "**Cliente:**", "**Lia:**", masked tool args; `--mask-user` masks the email in customer text.
- **Commit:** `feat: export sessions as Markdown transcripts`

### [ ] T28 — Eval case schema and cases file

- **Goal:** The 15 PRD §10 cases as validated YAML (design §13).
- **Files:** `src/.../evals/__init__.py`, `src/.../evals/cases.py`, `evals/cases.yaml`, `tests/unit/test_eval_cases.py`
- **FRs:** FR-01…FR-13 (eval coverage, PRD §10)
- **Acceptance criteria:**
  - [ ] Pydantic `EvalCase` / `Expect` schema per design §13; `load_cases(path)`.
  - [ ] 15 cases matching PRD §10, with `store_today` / `clock` where needed and PII in `must_not_include` for order cases.
  - [ ] `check_expectations(case, tool_calls, replies)` with accent-folded, case-insensitive matching.
- **Tests:** YAML loads with 15 unique IDs; every tool named in `must_call` exists in the registry; `check_expectations` pass/fail on hand-built inputs (substring, any-group, regex, `scope: all`, must-not-call).
- **Commit:** `test: add agent eval case schema and cases`

### [ ] T29 — Eval harness, report and `emporio eval`

- **Goal:** Run cases end to end and report pass/fail and latency (design §13).
- **Files:** `src/.../evals/harness.py`, `src/.../evals/report.py`, `src/.../cli.py`, `tests/agent/test_agent_eval.py`, `tests/unit/test_eval_harness.py`
- **FRs:** FR-14 (eval) (NFR-03)
- **Acceptance criteria:**
  - [ ] Per case: `Deps` with the case clock and `store_today`, temp checkpointer and handoff log, shared repo and index; `CaseResult`; LLM error → `error`; `EVAL_DELAY_S` between cases.
  - [ ] `emporio eval [--cases] [--case] [--report]` prints a Rich table, writes `var/eval-report.md` (pass rate, p50/p95, model, prompt version, date), exit 1 on any failure.
  - [ ] `tests/agent/test_agent_eval.py` parametrized over the YAML, marked `llm`, skipped without a key.
- **Tests:** harness with the fake model on a 2-case YAML → one pass, one fail, report rendered; p50/p95 computed on known latencies; `llm` test skips cleanly without a key.
- **Commit:** `feat: add eval harness, report and eval command`

### [ ] T30 — Live eval run and prompt tuning

- **Goal:** Run the real eval on Gemini Flash and fix failures through prompt/docstring changes only.
- **Files:** `src/.../agent/prompts.py`, `src/.../tools/*.py` (docstrings), `docs/design.md` (§9 if the prompt changed), `docs/eval-results.md`
- **FRs:** FR-01…FR-13 (behavioural check) (NFR-01, NFR-03, NFR-04)
- **Acceptance criteria:**
  - [ ] `uv run emporio eval` reaches at least 14/15 passing; any remaining failure is explained in `docs/eval-results.md`.
  - [ ] `PROMPT_VERSION` bumped if the prompt changed; design §9 updated to match.
  - [ ] p50/p95 latency recorded in `docs/eval-results.md`.
- **Tests:** none new (unit tests still green; `uv run pytest -m llm` matches the report).
- **Commit:** `fix: tune prompt and tool docstrings from eval results`

### [ ] T31 — Example conversations

- **Goal:** The 5 PRD §12 transcripts recorded from the real CLI.
- **Files:** `examples/01-violoes-ate-1000.md`, `examples/02-endereco-e-horario.md`, `examples/03-preco-promocao-multiturno.md`, `examples/04-devolucao-pedido-7.md` (both dates), `examples/05-fora-de-escopo.md`
- **FRs:** FR-01, FR-02, FR-05, FR-06, FR-07, FR-08, FR-11, FR-14 (export)
- **Acceptance criteria:**
  - [ ] Each file exported with `emporio export`, header states model and `STORE_TODAY`.
  - [ ] Facts in each transcript match PRD §12 (12 violões; R$ 2.089,05 and R$ 439,20; order 7 inside at 2026-02-20 and outside at 2026-03-23).
  - [ ] No raw customer email/phone in tool blocks.
- **Tests:** `tests/unit/test_examples.py`: 5 files exist; no tool block contains an unmasked customer email.
- **Commit:** `docs: add example conversations`

### [ ] T32 — README

- **Goal:** Reviewer-ready README covering every challenge deliverable (PRD §11).
- **Files:** `README.md`, `CLAUDE.md` (fill "App commands"), `docs/ai-usage-log.md`
- **FRs:** — (NFR-06; PRD §11)
- **Acceptance criteria:**
  - [ ] Sections: Overview, Setup (fresh clone → chat in 4 commands), Configuration (providers, `STORE_TODAY`, phone-matching rule), Usage (all CLI commands), Design decisions, Assumptions (link to PRD §4), Evaluation (how to run, latest results), Limitations and future work, AI-assisted workflow, LangSmith privacy warning.
  - [ ] Setup steps verified from a fresh clone in a temp dir.
- **Tests:** none (docs only); `uv run pytest` still green.
- **Commit:** `docs: write README`

### [ ] T33 — (Optional, stretch) Streamlit UI

- **Goal:** A minimal web chat over the same graph, only if time allows.
- **Files:** `src/.../ui/streamlit_app.py`, `pyproject.toml` (`ui` extra), `README.md`
- **FRs:** FR-11, FR-12 (same graph and checkpointer); stretch goal from PRD §2
- **Acceptance criteria:**
  - [ ] `uv sync --extra ui` then `uv run streamlit run …` opens a chat with session ID shown and resumable.
  - [ ] Optional tool-trace expander with masked args; no new business logic (reuses `build_deps`, `build_graph`, `run_turn`).
- **Tests:** import smoke test skipped when `streamlit` isn't installed.
- **Commit:** `feat: add optional Streamlit chat UI`

---

## Traceability

| Requirement | Tasks |
|---|---|
| FR-01 Product search | T03, T06, T09, T28, T30, T31 |
| FR-02 Price and promotion | T07, T10, T28, T30, T31 |
| FR-03 Availability | T05, T08, T09, T10, T28, T30 |
| FR-04 Order status with verification | T04, T12, T23, T28, T30 |
| FR-05 Store info and hours | T03, T13, T28, T30, T31 |
| FR-06 Policy questions | T15, T17, T18, T19, T23, T28, T30, T31 |
| FR-07 Routing data/policy/both | T11, T12, T19, T23, T24, T28, T30, T31 |
| FR-08 Out of scope | T06, T09, T23, T28, T30, T31 |
| FR-09 Unknown and empty results | T05, T06, T09, T10, T21, T23, T24 |
| FR-10 Prompt injection and persona | T23, T28, T30 |
| FR-11 Multi-turn context | T12, T23, T24, T28, T30, T31, T33 |
| FR-12 Conversation persistence | T24, T25, T26, T33 |
| FR-13 Human handoff | T04, T13, T14, T21, T23, T28, T30 |
| FR-14 CLI | T01, T18, T19, T21, T25, T26, T27, T29, T31 |
| NFR-01 Grounding | T23, T28, T30 |
| NFR-02 Privacy | T04, T12, T14, T20, T21, T26, T27 |
| NFR-03 Latency | T24, T29, T30 |
| NFR-04 Cost | T18, T22, T29, T30 |
| NFR-05 Provider-agnostic | T02, T22 |
| NFR-06 Reproducibility | T02, T16, T18, T25, T32 |
| NFR-07 Configuration | T02 |
| NFR-08 Observability | T20, T21, T24 |
| NFR-09 Quality | T01 (and every task's definition of done) |
