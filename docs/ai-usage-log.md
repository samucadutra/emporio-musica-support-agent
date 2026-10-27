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
