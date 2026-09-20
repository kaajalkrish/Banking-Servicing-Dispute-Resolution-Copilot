# Banking Servicing & Dispute-Resolution Copilot

Production-grade LangGraph multi-agent banking servicing copilot (BC-AAIE-HACK-01).
A supervisor routes retail-banking requests to specialist workers (intake,
account-servicing, dispute, product-info) over a custom MCP server, grounded in
policy and instrumented for observability, cost governance, security, compliance
and evaluation. **Gemini is the only model provider. No Docker, no external DB.**

> Status: **Phase 4 complete** (Phases 1-3 foundation + observability, plus
> security & guardrails: input/output guardrails, tool-scope enforcement,
> audit trail, secrets/PII scanners, red-team attack set). Later phases fill
> in the sections marked _(coming)_.

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
- `logs/agent_actions.jsonl` — the guardrail/audit trail (see Security above).
- `logs/mcp_transcript.jsonl` — every MCP tool call + resource read (masked).
- `logs/memory_test.log` — cross-session memory recall proof (masked; from a
  real Gemini + LangMem run — see above).
- `traces/phoenix_spans.parquet` — a full traced run's spans (§7.2 Trace export).
- `reports/secrets_scan.json`, `reports/pii_scan.json`,
  `reports/pii_redaction_sample.json`, `reports/redteam_results.json`,
  `docs/redteam-results.md` — Phase 4 scanner/red-team evidence (see Security
  above).
- Account and card numbers are always masked (`src/common/masking.py`); no PAN
  is ever written in plaintext.
- Tests write logs/state to a temp directory by default (Phoenix tracing is
  also disabled by default in tests — `PHOENIX_ENABLED=false`, set in
  `tests/conftest.py`), so the committed `logs/`/`traces/` hold only real,
  machine-generated evidence.

## Security & guardrails (Phase 4)

Every turn passes through `input_guard` before the supervisor and through the
output-guard chain in `finalize_node` before an answer is returned — these are
always wired in (`src/graph.py`), not opt-in.

- **Input guardrails** (`src/guardrails/`):
  - `pii.py` — Presidio (+ custom recognizers for our synthetic account-number
    and customer-id shapes) detects PII; `ingress.py`'s `sanitize_ingress()`
    masks it in the customer's raw message **before** it reaches the graph,
    any prompt, span or log (D-10) — `latest_user_text()` always prefers this
    sanitized text once ingress has run.
  - `injection.py` / `input.py` — policy-function pattern detection (no
    network dependency) for prompt injection, plus a cross-customer-reference
    check (a message naming a different customer id) and a length cap.
    `evaluate_input()` runs on the **raw** text (not yet PII-masked), since
    ingress's blanket customer-id masking would otherwise erase the digits
    the cross-customer check needs to compare.
  - A `block` decision short-circuits straight to `finalize` with a safe,
    reason-specific refusal — the supervisor and every worker are skipped
    entirely; `requires_human_review` is always set.
- **Tool-scope enforcement** (`src/tools/gateway.py`): every tool a worker
  calls is wrapped in a `ScopeGatewayTool` keyed to the authenticated
  `customer_id` (`src/agents/_common.py`'s `get_tool()`) — a `customer_id`
  argument that ever mismatches the authenticated one is denied and audited,
  never silently let through, even if a model tried to supply a different one.
- **Output guardrails** (`src/guardrails/output.py`), run in `finalize_node`
  before a `FinalAnswer` is built:
  - Any PAN/account number in the answer is masked unconditionally.
  - Another customer's id is blocked (the authenticated customer's own id is
    left alone).
  - Refund/dispute-outcome promises ("your refund has been approved", "your
    dispute has been approved") are rewritten to a drafted-for-human-review
    message — the copilot never commits an outcome (D-13).
  - A leaked system prompt is replaced with a safe refusal (not just flagged).
- **Output-risk tiers** (`src/guardrails/output_risk.py`): every answer is
  classified `low` / `medium` / `high` by which worker produced it (dispute
  and escalate_human are always `high` and always gated to human review,
  regardless of what the worker itself set — a backstop against a future bug
  forgetting to set `requires_human_review`).
- **Audit trail** (`src/guardrails/audit.py` → `logs/agent_actions.jsonl`):
  one masked JSON record per consequential action — `timestamp`, `run_id`,
  `actor`, `action`, `tool`, `decision`, `reason_code`, a hashed
  `customer_ref` (never the raw id), `details`. Written for every ingress
  sanitization/block, every gateway denial, every output sanitization, and
  every finalized answer.
- **Scanners:**
  - `python scripts/check_secrets.py` — flags Google/Gemini-style keys and
    generic token patterns in the working tree and full git history; verifies
    `.env` hygiene. Writes `reports/secrets_scan.json`; exits non-zero on any
    finding.
  - `python scripts/scan_evidence_for_pii.py` — searches `logs/`, `traces/`,
    `reports/`, `docs/` for Luhn-valid card numbers or full synthetic account
    numbers that should have been masked but weren't. Writes
    `reports/pii_scan.json`; exits non-zero on any finding.
  - `python scripts/pii_redaction_sample.py` — runs Presidio redaction over a
    handful of representative messages and writes a before/after sample to
    `reports/pii_redaction_sample.json` (D-14).
- **Red-team:** `python scripts/run_redteam.py` (also `python -m src.cli
  redteam`) runs `data/redteam/attacks.jsonl` (37 attacks across direct/
  indirect injection, cross-customer access, PAN exfiltration, system-prompt
  extraction, jailbreak roleplay, encoded-payload obfuscation and multi-turn
  setups — each tagged with an OWASP LLM Top 10 category) against the real
  guardrail functions and the real compiled graph with a scripted LLM — no
  live Gemini call needed. Writes `reports/redteam_results.json` and
  `docs/redteam-results.md`; a handful of encoded-payload attacks are
  documented, accepted gaps in the regex-based filter (not exploitable
  end-to-end, since nothing decodes/executes obfuscated text), everything
  else must actually pass or the harness exits non-zero.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full graph diagram
(including the memory/context nodes), the tiered-memory design, the
context-engineering strategies, and the agentic-RAG subgraph. Quick summary:

```
CLI → input_guard → load_memory → build_context → supervisor ─┬─ intake            (clarify ambiguous)
        │ (block: injection /                                 ├─ account_servicing (balance / transactions / statement / service requests)
        │  cross-customer /                                   ├─ dispute           (eligibility-checked, RAG-cited, draft for human review)
        │  too-long input)                                    ├─ product_info      (agentic RAG over the policy corpus, cites or abstains)
        │                                                      ├─ escalate_human    (out-of-scope / high-risk)
        └──────────────────────────────────────────────────────┴─ finalize (output guard + risk gate) → save_memory (structured FinalAnswer, persists new facts)
MCP server (stdio): 7 tools + dispute-windows resource, consumed via
langchain-mcp-adapters, every call scope-gated to the authenticated
customer_id. SQLite checkpointer for short-term memory; a step/recursion
guard stops runaway loops.
```

## Evaluation & cost governance (Phase 5)

- `python -m src.cli eval [--out PATH] [--limit N] [--no-score]` runs the
  golden set (`data/golden_set/golden.jsonl`, 47 authored cases; 30 is the
  scored target — see plan.md's note on why) through the live graph and
  scores it with DeepEval (`src/evaluation/harness.py`): hallucination,
  faithfulness, answer relevancy (Gemini judge, `src/evaluation/
  gemini_judge.py`), plus a custom accuracy metric comparing observed vs
  expected behavior. `regenerate --eval [--limit N]` does the same as part of
  a full regeneration.
- **Checkpointing**: after every case, progress is saved to
  `artifacts_regen/eval_checkpoint.json` (gitignored) and the real output
  path is rewritten too, so a crash or quota wall loses at most one case's
  work — rerunning the same command resumes automatically instead of
  starting over.
- `python -m src.observability.golden_signals [--project P] [--eval PATH]
  [--out PATH]` computes p50/p95 latency split by thinking/acting/tool
  (`src/observability/span_types.py`), token totals, a cost estimate
  (`src/observability/pricing.py` — per-model list prices copied from
  Google's published Gemini pricing page, with the source URL and the date
  confirmed recorded in the report; runs used the free tier, so the figure is
  the equivalent cost at paid Standard list price, not billed spend; a model
  with no confirmed price makes cost `null` with a note instead of a guess),
  request/error rate, and imports `accuracy`/`hallucination_rate` from an
  eval report.
- `reports/eval_report_initial.json` — the first, pre-fix evidence run (30
  cases, accuracy 0.6). `docs/failure-analysis.md` documents the 3 real
  failures it surfaced, each with a citation to a real `run_id` and tool-log
  record, root cause, and the commit that fixed it.
- `reports/dashboard_data.csv` — the full real span history underlying the
  Phoenix latency/cost/token dashboard (`python -m src.cli export --csv
  PATH`), deliberately not filtered to one clean run (the `.phoenix/`
  working directory is kept across every run specifically so this export
  reflects real failures too, not just successes).
- `python scripts/verify_citations.py <doc>... [--out PATH]` checks every
  cited `run_id`/`trace_id`/`span_id` in a Markdown doc actually resolves to
  a committed artifact (`traces/phoenix_spans.parquet` or `logs/*.jsonl`).

## Coming in later phases

- _Governance_ — risk register, model card, compliance mapping, output-risk _(Phase 6)_
- _Bonus_ — FastAPI streaming endpoint _(Phase 6)_
- _Optimization note_ — baseline vs. optimized profile comparison, ref-doc.md's
  optional §8.1 item _(deferred to last, Phase 5/6)_

## Scope

Containerized/cloud deployment, real core-banking connectivity and front-end
polish are out of scope (ref-doc.md §6.2).
