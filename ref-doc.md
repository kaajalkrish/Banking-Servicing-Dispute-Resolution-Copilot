# Banking Servicing & Dispute-Resolution Copilot — Production-Grade Multi-Agent System

*Business Case BC-AAIE-HACK-01 · Domain: Banking & Finance — Retail Servicing · Cross-cutting finale: Agentic Core + Context Engineering + MCP + Observability + Cost Governance + Security & Governance + Agent Evaluation*

---

## 1. Project Identity

| | |
|---|---|
| **Business Case Title** | Banking Servicing & Dispute-Resolution Copilot — Production-Grade Multi-Agent System |
| **Business Case ID** | BC-AAIE-HACK-01 |
| **Domain** | Banking & Finance — Retail Customer Servicing |
| **Project Type** | Agentic AI Engineer Pathway — Cross-Cutting Capstone Hackathon |

---

## 2. Engagement Overview

| | |
|---|---|
| **Duration** | 20 hours |
| **Format** | Team of 2–4 |
| **Evaluation Mode** | Automated review of the submitted Git repository against the Hackathon Rubric (7 categories / 100 marks), scored entirely from committed evidence in the repository. No live demo judging. |
| **Review Output** | Per-team Excel report (Summary, Categories, Scorecard, Detailed, Improvement). |
| **Grade Bands** | Merit 75–89 · Pass 60–74 · Not Yet Passed < 60 |

**What is evaluated:** a working LangGraph multi-agent system (foundation: context engineering, tiered memory, a custom MCP server, an agentic-RAG tool) that is then instrumented and governed — Arize Phoenix observability, cost & latency governance, guardrails & audit, governance/compliance documentation, and agent-level evaluation & testing. Every claim is scored from committed evidence.

**What is not evaluated:** the visual polish of any interface, generic unit-test volume, or which optional deployment path you use. Containerized/cloud deployment is out of scope for this cut.

---

## 3. Problem Statement & Expected Solution

### 3.1 Problem

A retail bank wants a servicing copilot that resolves everyday customer requests end to end — balance and transaction queries, disputed-transaction intake, product and fee questions, and simple service requests — by understanding intent, calling the right tools, grounding answers in policy, and remembering context across the conversation. That is the easy half. The hard half — and the point of this hackathon — is to make that agent production-ready: fully traced, cost- and latency-governed, guardrailed against injection and PII leakage, auditable, governed for compliance, and continuously evaluated. You build the agent AND the engineering discipline that lets a bank actually run it.

### 3.2 Your Role

Agentic AI Engineer. You build a LangGraph multi-agent copilot, then instrument it with Arize Phoenix, govern its cost and latency, harden it with guardrails and an audit trail, document its risk and compliance posture, and prove its behaviour with agent-level evaluation and tests — delivering every artifact as committed evidence.

### 3.3 Expected Solution

A working, instrumented multi-agent application delivered as a Git repository that demonstrates:

- A LangGraph graph: typed state, a supervisor routing customer requests to specialized worker agents (intake, account-servicing, dispute, product-info), conditional routing, checkpointing and structured output.
- A custom MCP server (≥ 2 tools + 1 resource) consumed via langchain-mcp-adapters, engineered context (write/select/compress/isolate + summarization + quarantine of untrusted customer text), tiered memory with verified cross-session persistence, and an agentic-RAG tool over a banking-policy corpus.
- Arize Phoenix instrumentation with a committed trace export, a machine-generated tool-invocation log, and an evidence-linked failure-mode analysis.
- A Phoenix-derived golden-signals report and a cost/latency dashboard; input/output guardrails, an audit trail and secrets hygiene; a governance pack (risk register, model card, compliance mapping, output-risk classification).
- Agent-level evaluation (LLM-as-judge + hallucination) and agent tests (routing-logic, loop/cascade guard, tool-contract), with a reproducible local-run runbook.

### 3.4 Applicable Rules

- **Evidence-in-Repo Rule.** Only committed artifacts are scored. A claim with no committed evidence scores zero; an evidence artifact with no producing code (a metric, trace or log a learner could hand-write) is heavily discounted.
- **Citation-Resolves Rule.** Wherever a document cites evidence (a Phoenix run/span id, a log record, a control file), the citation must resolve to a committed artifact. Unresolvable citations are treated as missing.
- **Synthetic-Data Rule.** Use only synthetic banking data you generate. Account numbers, card numbers (PANs) and PII must be synthetic and masked where shown; never write them to logs in plaintext.
- **Open-Source & Gemini-Only Rule.** Use the approved open-source stack with Google Gemini as the only model provider (not Claude). Build, run and evaluate with pip + Python — no Docker or external database service required for this cut.
- **Reproducibility Rule.** The system, its traces and its evaluation must be regenerable from a single documented command with committed sample inputs.

---

## 4. Technology & Framework Stack

Fixed open-source toolchain with Google Gemini as the only model provider. Everything installs with pip; no Docker or external DB service required.

| Layer | Approved tool (open source unless noted) |
|---|---|
| Language / Agent Framework | Python 3.11+ · LangGraph (MIT) |
| LLM Provider | Google Gemini (API) — the only approved provider; not Claude |
| Interoperability | MCP Python SDK (stdio) + langchain-mcp-adapters |
| Memory | langgraph-checkpoint-sqlite (SQLite file) + LangMem |
| Retrieval | Chroma or FAISS + Sentence-Transformers (local) |
| Observability (mandated) | Arize Phoenix + OpenTelemetry / openinference (local, in-process) |
| Evaluation | DeepEval (LLM-as-judge = Gemini) · pytest for agent tests |
| Security | Guardrails-AI / LLM Guard · Presidio (PII) · python-dotenv |
| Interface | CLI (required) · FastAPI streaming (optional / bonus) |

---

## 5. Acceptance Criteria & Non-Functional Requirements

### 5.1 Functional Acceptance Criteria

| ID | Criterion |
|---|---|
| AC-01 | A customer can request account information (balance, recent transactions, statement summary) and the copilot returns an accurate answer grounded in the data its tools return. |
| AC-02 | A customer can raise a disputed or unauthorized transaction; the copilot captures the dispute, checks eligibility against servicing policy, and drafts a resolution or the next step for a human agent. |
| AC-03 | A customer can ask a product, fee or servicing-policy question; the copilot answers grounded in the policy corpus with a citation, and abstains rather than guessing when the corpus does not support an answer. |
| AC-04 | The copilot identifies each request's intent and handles it with the right capability; ambiguous or out-of-scope requests are clarified or escalated to a human, not mishandled. |
| AC-05 | The copilot maintains context — it uses facts stated earlier in the conversation and recalls the customer's prior-session context on a return visit. |
| AC-06 | The copilot handles untrusted customer input safely: attempts to inject instructions or access another customer's data are refused, and account/card numbers are never exposed in answers or logs. |
| AC-07 | A machine-generated tool-invocation log (`logs/tool_calls.jsonl`) written by committed logging middleware; tool names reconcile with the agent/MCP code. |
| AC-08 | `docs/failure-analysis.md` documents ≥ 3 real failures from your own runs, each citing the Phoenix run_id + span_id (or a tool-log record) that shows it, plus root cause and fix. |
| AC-09 | A Phoenix-derived golden-signals report (latency incl. thinking/acting/tool, tokens, cost estimate, plus accuracy + hallucination rate from the eval) and a cost/latency dashboard (Phoenix screenshot + underlying data file). |
| AC-10 | Input/output guardrails wired into the agent's I/O path, and a machine-generated audit trail of agent actions (`logs/agent_actions.jsonl`). |
| AC-11 | A governance pack: risk register, model/system card, compliance mapping (EU AI Act / NIST AI RMF / DPDP) and output-risk classification — each mitigation/claim citing a committed control. |
| AC-12 | Agent evaluation: a DeepEval (or equivalent) report over a golden set (hallucination + faithfulness/relevance), and agent tests — routing-logic, loop/cascade guard, and tool-contract. |

### 5.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | No secrets/keys committed; env-var config with a committed `.env.example` and a `.gitignore` covering `.env`. |
| NFR-02 | Single documented command runs the copilot and a second regenerates the Phoenix traces and the evaluation; committed sample inputs. |
| NFR-03 | Untrusted free-text customer content is quarantined and never treated as instructions. |
| NFR-04 | Agent pipeline uses async where it calls tools/models; graceful degradation on tool/model failure (timeouts, retries, exit conditions). |
| NFR-05 | All data synthetic; PANs/account numbers masked and never logged in plaintext. |
| NFR-06 | Evidence artifacts (traces, logs, reports) are machine-generated by committed code; the code that produced each is committed alongside it. |
| NFR-07 | PR-driven Git history: ≥ 3 PR-driven merges (`git merge --no-ff`); no direct pushes to main. |

---

## 6. Functional Scope

### 6.1 In Scope

- The LangGraph multi-agent copilot (foundation) plus its full observability, cost-governance, security, governance and evaluation surface.
- Arize Phoenix tracing, golden-signals + cost/latency governance, guardrails + audit + secrets hygiene, governance/compliance docs, and agent-level evaluation & tests.
- A CLI to drive customer requests through the graph and to regenerate traces and the evaluation.

### 6.2 Out of Scope (this cut)

- Containerized / cloud deployment (Docker, Rancher, k8s) — deferred; do not spend hackathon time on it.
- Real core-banking connectivity or any real customer/account data.
- Front-end visual polish; generic unit-test volume for its own sake.
- Advanced OAuth flows and live secrets-rotation infrastructure (document the approach instead).

---

## 7. Required Artifacts — What to Commit

This is the checklist your submission is scored against. Each artifact must be present at (or near) the path shown and contain what is listed. Remember the Evidence-in-Repo and Citation-Resolves rules: outputs must be produced by committed code, and every citation must resolve to a committed artifact.

### 7.1 Agentic System — Foundation

| Area | Artifact (path) | Must contain |
|---|---|---|
| LangGraph graph | `src/graph.py` | Typed state; supervisor + ≥3 worker agents; conditional edges; checkpointer; structured output at node boundaries |
| MCP server | `mcp_server/` + `logs/mcp_transcript.jsonl` | ≥2 tools + 1 resource; consumed via langchain-mcp-adapters; committed tool-call transcript |
| Context engineering | `src/context/` | write/select/compress/isolate; summarization middleware; quarantine of untrusted text |
| Tiered memory | `src/memory/` + `tests/test_memory_persistence.py` + `logs/memory_test.log` | short + long/semantic memory; cross-session recall test with committed output log |
| Agentic-RAG tool | `src/tools/rag_tool.py` + `data/policy_corpus/` | retrieval-in-the-loop over a synthetic banking-policy corpus |

### 7.2 Observability & Tracing (Arize Phoenix — mandated)

| Area | Artifact (path) | Must contain |
|---|---|---|
| Phoenix instrumentation | `src/observability/tracing.py` | Phoenix/openinference tracer wired into the run path (called, not just imported) |
| Trace export | `traces/phoenix_spans.parquet` (or `.jsonl`) | ≥1 full run; spans across multiple agents + every tool call; latencies present |
| Tool-invocation log | `logs/tool_calls.jsonl` | machine-generated; per call: timestamp, agent/node, tool_name, args, result, latency_ms, status; names reconcile with code |
| Failure-mode analysis | `docs/failure-analysis.md` | ≥3 real failures, EACH citing Phoenix run_id + span_id (or tool-log record) + root cause + fix |

### 7.3 Performance & Cost Governance

| Area | Artifact (path) | Must contain |
|---|---|---|
| Golden-signals report | `reports/golden_signals.json` + producing script | Phoenix-derived latency (thinking/acting/tool), tokens in/out, cost estimate; accuracy + hallucination rate from the eval |
| Cost/latency dashboard | `reports/dashboard.png` + `reports/dashboard_data.csv` | Phoenix latency/cost/token dashboard screenshot AND the underlying data file it was drawn from |

### 7.4 Security & Guardrails

| Area | Artifact (path) | Must contain |
|---|---|---|
| Guardrail code | `src/guardrails/` | input/output guardrails wired into the agent's I/O path (blocks/sanitizes) |
| Audit trail | `logs/agent_actions.jsonl` + audit middleware | machine-generated: actor, action, tool, decision, timestamp for consequential actions |
| Secrets hygiene | `.env.example`, `.gitignore` | env-var config; .gitignore covers .env; no secrets committed anywhere |

### 7.5 Governance & Compliance (citation-gated)

| Area | Artifact (path) | Must contain |
|---|---|---|
| Risk register | `docs/risk-register.md` | risk, category (OWASP/NIST), likelihood, impact, mitigation (cite the committed control), residual risk, owner |
| Model / system card | `docs/model-card.md` | model (Gemini), data (synthetic), intended use, limitations, known failure modes (cite failure-analysis.md), out-of-scope |
| Compliance mapping | `docs/compliance.md` | applicable EU AI Act / NIST AI RMF / DPDP obligations → how addressed → evidence artifact |
| Output-risk classification | `docs/output-risk.md` | low/med/high output tiers + how high-risk is gated (human-in-loop / refusal) + a sample |

### 7.6 Agent Evaluation & Testing (lean, agent-specific)

| Area | Artifact (path) | Must contain |
|---|---|---|
| Evaluation report | `reports/eval_report.json` + harness | DeepEval (or equiv) over a golden set: hallucination + faithfulness/relevance; LLM-as-judge = Gemini |
| Routing-logic test | `tests/test_routing.py` | asserts conditional edges route the right worker for given states |
| Loop/cascade guard | `tests/test_loops.py` | asserts a max-steps / recursion-limit stops runaway loops |
| Tool-contract test | `tests/test_tool_contracts.py` | asserts each tool's input/output schema + one error path |

### 7.7 Engineering & Delivery

| Area | Artifact (path) | Must contain |
|---|---|---|
| Local-run runbook | `README.md` | single-command run; how to regenerate traces (Phoenix) and the eval; committed sample inputs |
| Git workflow | git history | ≥3 PR-driven merges (`git merge --no-ff`); no direct pushes to main |
| Bonus | `src/api/` (FastAPI streaming) | OPTIONAL: async FastAPI streaming endpoint — extra credit, not required |

---

## 8. Producing the Evidence — Format & Where to Obtain

Every evidence artifact must be produced by committed code and committed in the format shown below. This tells you the exact format and the tool / method to generate each one, so "observability" or "cost governance" becomes a concrete file you generate — not a slide. Enable Arize Phoenix locally (`pip install arize-phoenix openinference-instrumentation-langchain`; the UI runs at localhost:6006) — it is the single source your traces, latency, token and cost evidence come from.

| Artifact | Format | How to produce it / where to get it |
|---|---|---|
| Phoenix trace export | Parquet or JSONL of OTel spans | Turn on Phoenix tracing (openinference-instrumentation-langchain), run one full conversation, then export: `px.Client().get_spans_dataframe().to_parquet('traces/phoenix_spans.parquet')`. |
| Tool-invocation log | JSONL — one object per tool call | A logging wrapper/decorator on every tool that appends `{timestamp, agent, tool_name, args, result, latency_ms, status}` to `logs/tool_calls.jsonl` on each call. |
| Failure-mode analysis | Markdown | Open your Phoenix traces, pick ≥3 real failures, write each up citing its run_id + span_id, with root cause and the fix you applied. |
| Golden-signals report | JSON | A script reads the Phoenix spans (`get_spans_dataframe()`): p50/p95 latency split by span type (thinking / acting / tool), token totals from the LLM spans, cost = tokens × published price; import accuracy + hallucination rate from the eval report; write `reports/golden_signals.json`. |
| Cost/latency dashboard | PNG + CSV | Phoenix UI (localhost:6006) shows latency / cost / token dashboards — screenshot one; export the underlying data with `get_spans_dataframe().to_csv('reports/dashboard_data.csv')`. |
| Guardrail code | Python module | Guardrails-AI / LLM Guard validators (or policy functions) wrapped around the agent's input and output, wired into the graph's I/O nodes. |
| Audit trail | JSONL | Audit middleware that appends `{actor, action, tool, decision, timestamp}` for each consequential action to `logs/agent_actions.jsonl`. |
| Governance pack | Markdown | `risk-register.md`, `model-card.md`, `compliance.md`, `output-risk.md` — each entry cites the committed control/artifact it refers to. |
| Evaluation report | JSON | A DeepEval run over your golden set (hallucination, faithfulness, answer-relevance; LLM-as-judge) that writes `reports/eval_report.json`, plus the harness that produced it. |
| Agent tests | pytest files | `tests/test_routing.py` (assert conditional-edge routing), `tests/test_loops.py` (assert a recursion/step limit stops loops), `tests/test_tool_contracts.py` (assert each tool's I/O schema + one error path). |

### 8.1 Good-to-Have

- FastAPI streaming endpoint; a demonstrated local run (screenshot/log).
- PII-redaction middleware (Presidio) with a before/after sample; a small red-team attack set + results.
- An optimization note showing a measured before/after latency or cost improvement (two Phoenix-derived reports).

---

*On completion you will have demonstrated the skill the industry actually screens for: not just building a LangGraph agent, but making it observable, cost-governed, secure, compliant and continuously evaluated — the full production surface of an agentic system, proven with committed evidence rather than a demo that worked once.*
