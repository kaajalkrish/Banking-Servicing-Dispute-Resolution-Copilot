# Banking Servicing & Dispute-Resolution Copilot

Production-grade LangGraph multi-agent banking servicing copilot (BC-AAIE-HACK-01).
A supervisor routes retail-banking requests to specialist workers (intake,
account-servicing, dispute, product-info) over a custom MCP server, grounded in
policy and instrumented for observability, cost governance, security, compliance
and evaluation. **Gemini is the only model provider. No Docker, no external DB.**

> Status: **Phase 3 complete** (Phases 1-2 foundation + Arize Phoenix
> observability: tracing, tool-invocation log, trace export). Later phases
> fill in the sections marked _(coming)_.

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
> requests/day per project; flash-lite has its own separate daily quota **and**
> a 15-requests/minute cap. A single conversation turn can make several real
> calls (routing, worker composition, RAG grading/answer, memory extraction),
> so a full batch over many conversations can burst past 15/min — the retry
> wrapper (`src/llm.py`) backs off and recovers, but budget real wall-clock
> time for a full `regenerate` run. Prefer `GEMINI_MODEL_FAST` for routing/
> cheap calls and local testing; batch live verifications together.

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

## Observability (Phase 3)

Every `chat`/`run`/`mcp-demo`/`regenerate` invocation calls Phoenix tracing on
the run path (not just imports it). Start the app yourself to watch live:

```bash
python -m src.cli chat --customer-id C0001 --message "What is my balance?"
# then open http://localhost:6006 in a browser
```

- **Working directory:** `.phoenix/` at the repo root (gitignored), so traces
  persist across separate process runs — a later `export`/`regenerate` can
  read spans written by an earlier, already-exited process.
- **`run_id`:** a UUID minted once per turn (`src/common/ids.py`), stamped as
  `attributes.metadata.run_id` on every span in that turn (and as
  `attributes.session.id` when no LangGraph thread is in play — inside a real
  conversation thread, LangGraph's own instrumentation sets `session.id` to
  the thread id instead, which usefully groups a whole conversation in the
  Phoenix UI). **Cite `metadata.run_id`, not `session.id`, for a failure
  citation** — verified against real captured spans, not assumed.
- **Span-type mapping** (`src/observability/span_types.py`, for golden
  signals in Phase 5): `LLM` → thinking; `TOOL`/`RETRIEVER` → tool; everything
  else (`CHAIN`, `AGENT`) → acting. Verified against real spans from two live
  runs, not generic conventions.
- **`export`:** `python -m src.cli export [--project NAME] [--parquet PATH] [--csv PATH]`
  — reads spans from `.phoenix/` (relaunching the local app if needed) and
  writes parquet/CSV, JSON-stringifying any dict-valued column first (parquet
  can't store a dict in a cell).
- **`regenerate`:** `python -m src.cli regenerate --traces [--inputs PATH] [--commit-evidence] [--keep-ui]`
  re-runs the sample conversations and exports spans. **Evidence policy
  (D-06):** by default everything goes to gitignored `artifacts_regen/`
  (`traces/`, `logs/`) so experiments never touch committed evidence;
  `--commit-evidence` redirects to the real `traces/` and `logs/` paths
  instead. `--keep-ui` leaves the process (and the local Phoenix server)
  running afterwards for a dashboard screenshot (Phase 5).
- **Verify:** `python scripts/verify_tool_names.py` (logged tool names
  reconcile with the code) and `python scripts/verify_trace_export.py`
  (multi-agent + tool-call coverage, latencies, run_id all present in a
  committed export).

## Logs & evidence

- `logs/tool_calls.jsonl` — every tool call, resilience+logging-wrapped
  (`src/tools/registry.py`): timestamp, run_id, agent, tool_name, args,
  result, latency_ms, status.
- `logs/mcp_transcript.jsonl` — every MCP tool call + resource read (masked).
- `logs/memory_test.log` — cross-session memory recall proof (masked; from a
  real Gemini + LangMem run — see above).
- `traces/phoenix_spans.parquet` — a full traced run's spans (§7.2 Trace export).
- Account and card numbers are always masked (`src/common/masking.py`); no PAN
  is ever written in plaintext.
- Tests write logs/state to a temp directory by default (Phoenix tracing is
  also disabled by default in tests — `PHOENIX_ENABLED=false`, set in
  `tests/conftest.py`), so the committed `logs/`/`traces/` hold only real,
  machine-generated evidence.

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

- _Security_ — input/output guardrails, audit trail, Presidio PII, red-team _(Phase 4)_
- _Evaluation & cost_ — DeepEval (Gemini judge), golden signals, dashboard _(Phase 5)_
- _Governance_ — risk register, model card, compliance mapping, output-risk _(Phase 6)_
- _Bonus_ — FastAPI streaming endpoint _(Phase 6)_
- _Regenerate evaluation_ added to the `regenerate` command _(Phase 5)_

## Scope

Containerized/cloud deployment, real core-banking connectivity and front-end
polish are out of scope (ref-doc.md §6.2).
