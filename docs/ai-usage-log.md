# AI usage log

Tool: Claude Code (Opus). One or two lines per phase: what was asked, what changed by hand, what the assistant got wrong.

## Phase 2.5: Data inventory
- Claude Code inspected `data/` read-only with `scripts/inspect_data.py` and wrote `docs/data-inventory.md`. A follow-up pass answered the open questions with recommendations, and they were recorded as decisions D1–D11 in its §9.

## Phase 3: PRD
- In plan mode, Claude Code drafted `docs/prd.md` from the challenge and the inventory. It asked 3 questions (persona name, handoff mechanism, emoji policy); I chose a named persona "Lia", a handoff tool with a local log, and sparing emoji.
- In self-review it caught a "show up to 10 results" rule that would have cut the 12-item violões example, and an invented stock-quantity rule; both were fixed before review.

## Phase 4: Design
- In plan mode, Claude Code drafted `docs/design.md` from the PRD. It asked 3 questions (embedding model, how to build the agent graph, default LLM); I chose local fastembed embeddings, an explicit LangGraph `StateGraph`, and `gemini-2.5-flash`.
- While checking the data it found that ranking alternatives by price alone would not suggest the 7-string 112 for product 113, so the design ranks by name features first. The PRD's FR-14 gained the `eval`, `export` and `sessions` commands.

## Phases T01–T27: implementation
- Not logged here yet. The author should fill in this section from their own review notes (what was asked, what was changed by hand, what the assistant got wrong), since the log must reflect the author's experience.

## T28–T30: agent eval
- In plan mode, Claude Code designed the eval case schema, harness and `emporio eval` from design §13, then wrote the 15 cases. It flagged before starting that T30 needed a live API key, and did not tick T30 without one.
- Live run: the default model `gemini-2.5-flash` returned 404 for a new key. Claude Code found a working model, then hit the free-tier daily limit (about 20 requests per model) and split the cases across models. It reported the split run as such, not as a single clean run.
- It got two things wrong: two case checks were too strict for correct replies ("conferida", "encerrou"), and a plain `pytest` started running live-model tests once a key was in `.env` (it hung until the tests were limited with `-m "not llm"`). The one real behaviour fix was a prompt rule to refuse explicitly when asked to break a rule.

## T31–T33: examples, README and UI
- Examples were recorded from the real CLI across several models. Three first takes were rejected and re-recorded: one opened a handoff ticket without being asked, one skipped half of the question ("cordas"), and one lost its replies to quota.
- The exported header showed `STORE_TODAY: not set` for sessions recorded with `--store-today`, because `export` reads the environment; the fix was to pass `STORE_TODAY` when exporting, and this is documented in the README.
- The default model was changed to `gemini-3.8-flash` as a spec change (config, `.env.example`, design) after the old default stopped working for new keys.

