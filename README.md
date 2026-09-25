# Banking Servicing & Dispute-Resolution Copilot

A LangGraph multi-agent copilot for retail-banking servicing. A supervisor routes
each customer request to a specialist worker (intake, account servicing, dispute,
product info, or human escalation). The workers use a custom MCP server for
account data, and answers to policy questions are grounded in a policy library
with citations. Every turn is guarded, traced and auditable.
**Gemini is the only model provider. No Docker, no external database.**

- **Multi-agent routing:** a supervisor plus five workers; disputes are drafted
  for a human to decide, never approved by the copilot.
- **Custom MCP server:** 7 tools and a dispute-windows resource, every call scoped
  to the authenticated customer.
- **Agentic RAG:** retrieval over a policy corpus that cites its sources or
  abstains.
- **Memory:** per-thread conversation state and long-term per-customer facts.
- **Guardrails:** input, tool-scope and output guards, risk tiers and an audit
  trail.
- **Observability:** Phoenix tracing, tool-call logs and cost/latency signals.
- **Evaluation:** DeepEval over a golden set, plus a red-team suite.
- **Three interfaces:** a CLI, a streaming HTTP API and a Streamlit chat UI.

All data is synthetic. No real customer or account data is used.

## Architecture

```
CLI / API / UI → input_guard → load_memory → build_context → supervisor ─┬─ intake            (clarify ambiguous)
        │ (block: injection /                                           ├─ account_servicing (balance / transactions / statement / service requests)
        │  cross-customer /                                             ├─ dispute           (eligibility-checked, RAG-cited, draft for human review)
        │  too-long input)                                              ├─ product_info      (agentic RAG over the policy corpus, cites or abstains)
        │                                                               ├─ escalate_human    (out-of-scope / high-risk)
        └───────────────────────────────────────────────────────────────┴─ finalize (output guard + risk gate) → save_memory
```

The MCP server (stdio) is consumed through `langchain-mcp-adapters`. Short-term
memory uses a SQLite checkpointer, and a step/recursion guard stops runaway
loops. See [`docs/architecture.md`](docs/architecture.md) for the full graph,
trust boundaries, memory design and the RAG subgraph.

## Setup

**Prerequisites**

- Python 3.11+ (developed on 3.12)
- A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
  (a valid key starts with `AIza`)
- First-run downloads (one time, need internet): the Sentence-Transformers model
  `all-MiniLM-L6-v2` (~90 MB, used by the policy index and long-term memory
  search) and the spaCy English model that Presidio loads (`en_core_web_lg`).
  Expect a delay on the first guarded turn.

**Install**

```bash
python -m venv .venv
# Windows (Git Bash):  source .venv/Scripts/activate
# PowerShell:          .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Configure**

```bash
cp .env.example .env          # then set GOOGLE_API_KEY=AIza...  (.env is gitignored)
```

Optional overrides (safe defaults otherwise): `GEMINI_MODEL`
(`gemini-3.5-flash`), `GEMINI_MODEL_FAST` (`gemini-3.5-flash-lite`), `LOG_DIR`,
`STATE_DIR`, `MAX_STEPS`, `RECURSION_LIMIT`, and for the API `API_HOST`,
`API_PORT`, `API_TURN_TIMEOUT_S` (default 120 s). See `.env.example`.

> **Gemini quota note:** on the free tier the flash model is capped at 20
> requests/day per project, and flash-lite has its own daily quota and a
> 15-requests/minute cap. One turn can make several calls (routing, worker,
> RAG grading, memory extraction), so batch runs can hit the cap; the retry
> wrapper in `src/llm.py` backs off and recovers, but budget wall-clock time.

**Generate the synthetic data and build the policy index**

```bash
python scripts/generate_synthetic_data.py --seed 42   # deterministic
python scripts/build_policy_index.py                  # needed for policy questions
```

The policy index is safe to rebuild after editing `data/policy_corpus/*.md`
(chunk ids are deterministic, so it upserts).

## Run

### CLI

```bash
python -m src.cli chat --customer-id C0001                                # interactive
python -m src.cli chat --customer-id C0001 --message "What is my balance?"  # one-shot
python -m src.cli run --inputs data/sample_inputs/conversations.jsonl       # batch
python -m src.cli mcp-demo                                                  # MCP tools, no LLM
```

The chat starts by telling the customer they are talking to an automated AI
assistant that cannot approve refunds or disputes.

### Streamlit UI

```bash
python -m src.ui             # or: streamlit run src/ui/app.py
```

Open http://127.0.0.1:8501. This one command also starts the streaming API in
the background if it is not already running. The API takes about a minute to
load; until then the sidebar shows "API not ready yet" and the chat box is
disabled, and both switch to ready by themselves. `python -m src.ui --no-api`
skips starting the API.

Pick a synthetic customer in the sidebar and ask a question. Each turn shows
live progress by node name (never node content, since a worker's draft has not
yet passed the output guard), then the answer, its sources, its risk tier and a
"flagged for human review" warning when one applies. The UI is a thin client of
the API (`src/ui/client.py`) and never imports the graph, so every control
applies unchanged.

### Streaming API

```bash
python -m src.api            # http://127.0.0.1:8000  (API_HOST / API_PORT)
curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "C0001", "message": "What is my balance?"}'
```

`POST /chat/stream` returns server-sent events: `start` (with the AI disclosure
and the `run_id`), one `progress` event per graph node, and a `final` answer. A
failure adds an `error` event and still ends with a safe, human-review `final`.
`GET /health` reports liveness without a model call. It runs the same graph as
the CLI, so guardrails, audit and tracing are identical.
`python scripts/demo_api.py` streams sample conversations and writes
`logs/api_demo.log`.

**There is no authentication** in the API or the UI: the customer id they are
given is trusted, exactly like the CLI's `--customer-id`. They bind to loopback
by default and must not be exposed (`docs/security-approach.md`).

## Memory and context

- **Short-term (thread):** the LangGraph SQLite checkpointer persists full state
  per conversation thread (`data/state/checkpoints.sqlite`, gitignored).
- **Long-term (semantic):** LangMem with Gemini extracts durable facts (stated
  preferences, prior dispute references) into a per-customer namespace stored in
  a LangGraph `AsyncSqliteStore` (`data/state/memory.sqlite`, gitignored). They
  are recalled at the start of a turn and surfaced in each worker's prompt.
- Cross-session recall can be checked with
  `pytest tests/test_memory_persistence.py -m live -q` (writes
  `logs/memory_test.log`), or with the two-thread scenario in
  `data/sample_inputs/conversations.jsonl` (`conv-return-visit-session1` then
  `conv-return-visit-session2`).

## Observability

Every `chat`, `run`, `mcp-demo` and `regenerate` invocation starts Phoenix
tracing. To watch live, run a chat and open http://localhost:6006.

- Traces persist in `.phoenix/` (gitignored), so a later export can read spans
  from an earlier run.
- Each turn gets a `run_id` (`src/common/ids.py`), stamped as
  `attributes.metadata.run_id` on every span. Cite `metadata.run_id`, not
  `session.id`, when referring to a turn.
- Spans are classified as thinking (`LLM`), tool (`TOOL`/`RETRIEVER`) or acting
  (everything else) in `src/observability/span_types.py`.
- `python -m src.cli export [--project NAME] [--parquet PATH] [--csv PATH]`
  writes the spans to parquet/CSV.
- `python -m src.cli regenerate --traces --eval [--limit N] [--commit-evidence]`
  replays the 14 sample conversations (15 turns) through the traced graph,
  exports the spans and scores the golden set. By default it writes to
  gitignored `artifacts_regen/`; `--commit-evidence` overwrites the committed
  `traces/` and `logs/`. Use `--limit` for a smoke run.
- `python scripts/verify_tool_names.py` and `python scripts/verify_trace_export.py`
  check that logged tool names match the code and that the committed export
  covers agents, tool calls, latencies and `run_id`.

**Logs and evidence**

- `logs/tool_calls.jsonl`: every tool call with timestamp, run id, agent, tool,
  arguments, result, latency and status.
- `logs/agent_actions.jsonl`: the guardrail and audit trail.
- `logs/mcp_transcript.jsonl`: every MCP tool call and resource read (masked).
- `logs/memory_test.log`: cross-session memory recall proof.
- `traces/phoenix_spans.parquet`: a full traced run's spans.
- `reports/`: secrets and PII scans, red-team results, evaluation and cost
  reports, dashboard data.

Account and card numbers are always masked (`src/common/masking.py`); no card
number is ever written in plaintext.

## Security and guardrails

Every turn passes through `input_guard` before the supervisor and through the
output-guard chain in `finalize` before an answer is returned. Both are always
wired in (`src/graph.py`).

- **Input guard** (`src/guardrails/`): Presidio (plus custom recognizers for
  account-number and customer-id shapes) masks PII in the customer's message
  before it reaches the graph, a prompt, a span or a log. Pattern-based
  prompt-injection detection, a cross-customer-reference check and a length cap
  run on the raw text. A `block` decision skips the supervisor and every worker
  and returns a safe refusal flagged for human review.
- **Tool-scope enforcement** (`src/tools/gateway.py`): every tool call is checked
  against the authenticated `customer_id`. A mismatch is denied and audited, even
  if a model tried to supply a different id.
- **Output guard** (`src/guardrails/output.py`): masks any card or account number,
  blocks another customer's id, rewrites refund or dispute-outcome promises into a
  drafted-for-human-review message, and replaces a leaked system prompt with a
  safe refusal.
- **Output-risk tiers** (`src/guardrails/output_risk.py`): every answer is `low`,
  `medium` or `high`. Dispute and human-escalation answers are always `high` and
  always gated to human review.
- **Audit trail** (`src/guardrails/audit.py` to `logs/agent_actions.jsonl`): one
  masked JSON record per consequential action, with a hashed customer reference
  (never the raw id).
- **Scanners:** `python scripts/check_secrets.py` (keys and tokens in the tree and
  git history), `python scripts/scan_evidence_for_pii.py` (unmasked card or
  account numbers in committed evidence) and `python scripts/pii_redaction_sample.py`
  (before/after redaction sample). The first two exit non-zero on any finding.
- **Red team:** `python -m src.cli redteam` runs 37 attacks
  (`data/redteam/attacks.jsonl`: direct and indirect injection, cross-customer
  access, card-number exfiltration, system-prompt extraction, jailbreak
  roleplay, encoded payloads, multi-turn setups, each tagged with an OWASP LLM
  Top 10 category) against the real guardrails and graph with a scripted LLM, so
  no Gemini calls are needed. Results are in `reports/redteam_results.json` and
  `docs/redteam-results.md`. A few encoded-payload attacks are documented gaps in
  the regex-based filter.

## Evaluation and cost

- `python -m src.cli eval [--out PATH] [--limit N] [--no-score]` runs the golden
  set (`data/golden_set/golden.jsonl`) through the live graph and scores it with
  DeepEval (`src/evaluation/harness.py`): hallucination, faithfulness and answer
  relevancy (Gemini judge), plus a custom accuracy metric.
- Progress is checkpointed after every case to `artifacts_regen/eval_checkpoint.json`,
  so a crash or quota wall loses at most one case and rerunning resumes.
- `python -m src.observability.golden_signals` computes p50/p95 latency by
  thinking/acting/tool, token totals, a cost estimate (`src/observability/pricing.py`,
  from Google's published Gemini prices; runs used the free tier, so this is the
  equivalent paid cost, not billed spend), request/error rate, and accuracy and
  hallucination rate from an eval report.
- The committed evaluation (`reports/eval_report_initial.json`, accuracy 0.6) is
  the first run. `docs/failure-analysis.md` documents the three real failures it
  surfaced, each with a `run_id`, root cause and fix.
- Phoenix shows cost as `$0` because it has no per-model prices configured and the
  runs used the free tier; the real estimate is in `reports/golden_signals.json`.
- `python scripts/verify_citations.py <doc>...` checks that every cited run,
  trace and span id, control id and repository path in a document resolves to a
  committed artifact.

## Testing

```bash
pytest -q -m "not live"     # offline, deterministic (fake LLMs); the default
pytest -q -m live           # calls real Gemini (needs GOOGLE_API_KEY, spends quota)
```

Use `-m "not live"` for routine runs. The core agent tests are
`tests/test_routing.py`, `tests/test_loops.py` and `tests/test_tool_contracts.py`.
The UI is covered offline by `tests/test_ui_client.py`, `tests/test_ui_app.py`
and `tests/test_ui_launcher.py`. Tests write logs and state to a temp directory
and disable Phoenix tracing (`tests/conftest.py`), so the committed `logs/` and
`traces/` hold only real, machine-generated evidence.

## Documentation

| Document | What it covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Final graph, trust boundaries, tool and MCP layout, model and library versions |
| [`docs/control-catalog.md`](docs/control-catalog.md) | 26 controls with stable IDs (`CTL-01` ...), each with a code path and an evidence artifact |
| [`docs/risk-register.md`](docs/risk-register.md) | 17 risks (OWASP LLM Top 10 / NIST AI RMF) with likelihood, impact, mitigation and residual risk |
| [`docs/model-card.md`](docs/model-card.md) | Models, synthetic data, intended and out-of-scope use, human oversight, limitations |
| [`docs/compliance.md`](docs/compliance.md) | EU AI Act, NIST AI RMF and India DPDP Act mapped to controls, with status and gaps (not legal advice) |
| [`docs/security-approach.md`](docs/security-approach.md) | How real authentication, secrets rotation, breach handling and erasure would work (described, not built) |
| [`docs/failure-analysis.md`](docs/failure-analysis.md) | Three real failures with run ids, root cause and fix |
| [`docs/redteam-results.md`](docs/redteam-results.md) | Red-team results by attack category |

## Repository layout

```
src/graph.py, cli.py, llm.py   graph wiring, CLI, Gemini wrapper with retry
src/mcp_client.py              MCP client (loads the MCP server's tools)
src/agents/                    supervisor and workers
src/context/, src/memory/      context engineering, short- and long-term memory
src/tools/                     RAG tool, scope gateway, tool registry
src/guardrails/                input, output, risk tiers, audit, PII, injection
src/observability/             tracing, span types, golden signals, pricing
src/evaluation/                DeepEval harness and Gemini judge
src/api/, src/ui/              streaming API and Streamlit UI
mcp_server/                    the custom MCP server
data/                          synthetic data, policy corpus, golden set, red-team attacks
scripts/                       data generation, index build, scanners, verifiers, demos
docs/, logs/, traces/, reports/  documentation and committed evidence
tests/                         offline and live tests
```

## Scope

Containerized or cloud deployment, real core-banking connectivity, real
authentication and front-end polish are out of scope. Known gaps (consent,
data-principal rights, authentication) are listed in `docs/compliance.md` and
`docs/security-approach.md`.
