# Banking Servicing & Dispute-Resolution Copilot

Production-grade LangGraph multi-agent banking servicing copilot (BC-AAIE-HACK-01).
A supervisor routes retail-banking requests to specialist workers (intake,
account-servicing, dispute, product-info) over a custom MCP server, grounded in
policy and instrumented for observability, cost governance, security, compliance
and evaluation. **Gemini is the only model provider. No Docker, no external DB.**

> Status: **Phase 1 complete** (foundation: MCP server, LangGraph graph, CLI,
> synthetic data, agent tests). Later phases fill in the sections marked _(coming)_.

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
(`gemini-2.5-flash`), `GEMINI_MODEL_FAST` (`gemini-2.5-flash-lite`), `LOG_DIR`,
`STATE_DIR`, `MAX_STEPS`, `RECURSION_LIMIT`. See `.env.example`.

## Generate synthetic data

All data is synthetic (no real customer/account data). Regenerate deterministically:

```bash
python scripts/generate_synthetic_data.py --seed 42
```

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

## Logs & evidence

- `logs/mcp_transcript.jsonl` — every MCP tool call + resource read (masked).
- Account and card numbers are always masked (`src/common/masking.py`); no PAN
  is ever written in plaintext.
- Tests write logs to a temp directory, so the committed `logs/` holds only
  real, machine-generated evidence.

## Architecture (Phase 1)

```
CLI → supervisor ─┬─ intake            (clarify ambiguous)
                  ├─ account_servicing (balance / transactions / statement)
                  ├─ dispute           (draft dispute for human review)
                  ├─ product_info      (fees; RAG in Phase 2)
                  ├─ escalate_human    (out-of-scope / high-risk)
                  └─ finalize          (structured FinalAnswer)
MCP server (stdio): 6 tools + dispute-windows resource, consumed via
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
