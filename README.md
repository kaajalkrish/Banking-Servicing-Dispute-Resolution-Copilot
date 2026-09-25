# Banking Servicing & Dispute-Resolution Copilot

Production-grade LangGraph multi-agent banking servicing copilot (BC-AAIE-HACK-01).
A supervisor routes retail-banking requests to specialist workers (intake,
account-servicing, dispute, product-info) over a custom MCP server, grounded in
policy and instrumented for observability, cost governance, security, compliance
and evaluation. **Gemini is the only model provider. No Docker, no external DB.**

> Status: **Phase 2 complete** (Phase 1 foundation + agentic RAG over a policy
> corpus, context engineering, and tiered short/long-term memory). Later
> phases fill in the sections marked _(coming)_.

## Prerequisites

- Python 3.11+ (developed on 3.12)
- A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
  (a valid key starts with `AIza`)

## Install

```bash
python -m venv .venv
# Windows (Git Bash):  source .venv/Scripts/activate
# PowerShell:          .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure

```bash
cp .env.example .env          # then edit .env
# set GOOGLE_API_KEY=AIza...   (the real .env is gitignored; never commit it)
```

Optional overrides (safe defaults applied otherwise): `GEMINI_MODEL`
(`gemini-3.5-flash`), `GEMINI_MODEL_FAST` (`gemini-3.5-flash-lite`), `LOG_DIR`,
`STATE_DIR`, `MAX_STEPS`, `RECURSION_LIMIT`. See `.env.example`.

> **Gemini free-tier quota note:** the flash-tier model is capped at 20
> requests/day per project on the free tier. Prefer `GEMINI_MODEL_FAST`
> (flash-lite, a separate quota) for routing/cheap calls and for local testing
> where possible; batch live verifications together rather than one-off runs.

## Generate synthetic data

All data is synthetic (no real customer/account data). Regenerate deterministically:

```bash
python scripts/generate_synthetic_data.py --seed 42
```

## Build the policy index (agentic RAG)

Required before `product_info`/`dispute` policy questions can be answered
(they abstain gracefully if the index doesn't exist yet, but won't have
anything to cite):

```bash
python scripts/build_policy_index.py
```

Rebuilding after editing a `data/policy_corpus/*.md` file is safe to re-run —
chunk ids are deterministic, so it upserts rather than duplicates. **First run
downloads the local Sentence-Transformers embedding model** (~90MB from
Hugging Face); this also backs the long-term memory store's semantic search,
so it only downloads once for both.

## Run the copilot

```bash
# One-shot:
python -m src.cli chat --customer-id C0001 --message "What is my balance?"

# Interactive:
python -m src.cli chat --customer-id C0001

# Batch over the committed sample conversations:
python -m src.cli run --inputs data/sample_inputs/conversations.jsonl

# Exercise the MCP tools directly (no LLM) and write the transcript:
python -m src.cli mcp-demo
```

## Test

```bash
pytest -q -m "not live"     # offline, deterministic (fake LLMs); the default
pytest -q -m live           # tests that call real Gemini (need GOOGLE_API_KEY)
```

## Memory & context (Phase 2)

- **Short-term (thread):** the LangGraph SQLite checkpointer persists full
  state per conversation thread (`data/state/checkpoints.sqlite`, gitignored).
- **Long-term (semantic):** LangMem + Gemini extract durable facts (stated
  preferences, prior dispute references) into a per-customer namespace,
  persisted via a LangGraph `AsyncSqliteStore` (`data/state/memory.sqlite`,
  gitignored). Recalled automatically at the start of a turn and surfaced in
  each worker's prompt — see `docs/architecture.md` for the full flow.
- Verify cross-session recall yourself: `pytest tests/test_memory_persistence.py -m live -q`
  (writes `logs/memory_test.log`), or try the two-thread scenario in
  `data/sample_inputs/conversations.jsonl` (`conv-return-visit-session1` then
  `conv-return-visit-session2`).

## Logs & evidence

- `logs/mcp_transcript.jsonl` — every MCP tool call + resource read (masked).
- `logs/memory_test.log` — cross-session memory recall proof (masked; from a
  real Gemini + LangMem run — see above).
- Account and card numbers are always masked (`src/common/masking.py`); no PAN
  is ever written in plaintext.
- Tests write logs/state to a temp directory by default, so the committed
  `logs/` holds only real, machine-generated evidence.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full graph diagram
(including the memory/context nodes), the tiered-memory design, the
context-engineering strategies, and the agentic-RAG subgraph. Quick summary:

```
CLI → load_memory → build_context → supervisor ─┬─ intake            (clarify ambiguous)
                                                 ├─ account_servicing (balance / transactions / statement / service requests)
                                                 ├─ dispute           (eligibility-checked, RAG-cited, draft for human review)
                                                 ├─ product_info      (agentic RAG over the policy corpus, cites or abstains)
                                                 ├─ escalate_human    (out-of-scope / high-risk)
                                                 └─ finalize → save_memory (structured FinalAnswer, then persists new facts)
MCP server (stdio): 7 tools + dispute-windows resource, consumed via
langchain-mcp-adapters. SQLite checkpointer for short-term memory; a
step/recursion guard stops runaway loops.
```

## Coming in later phases

- _Observability_ — Arize Phoenix tracing, tool-invocation log, trace export _(Phase 3)_
- _Security_ — input/output guardrails, audit trail, Presidio PII, red-team _(Phase 4)_
- _Evaluation & cost_ — DeepEval (Gemini judge), golden signals, dashboard _(Phase 5)_
- _Governance_ — risk register, model card, compliance mapping, output-risk _(Phase 6)_
- _Bonus_ — FastAPI streaming endpoint _(Phase 6)_
- _Regenerate traces + evaluation_ with a single command _(Phase 3/5)_

## Scope

Containerized/cloud deployment, real core-banking connectivity and front-end
polish are out of scope (ref-doc.md §6.2).
