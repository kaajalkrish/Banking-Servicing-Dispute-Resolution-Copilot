# Submission Check against `ref-doc.md`

Banking Servicing & Dispute-Resolution Copilot (BC-AAIE-HACK-01). A line-by-line
comparison of this repository against `ref-doc.md`, with the proof and its
location for every requirement, the phase that delivered it, and a plain
statement of anything missing.

## 0. How to read this document

**Legend.** ✅ the `ref-doc.md` line is met, with proof (a caveat, if any, is
written in the row's text or Weakness column; it does not mean the requirement is
unmet) · ⚠️ only partly met or not demonstrated · ⏳ not done yet, and it cannot
be done locally · ❌ not done · ➖ not applicable.

**Phases.** P1 foundation · P2 context/memory/RAG · P3 observability · P4
security · P5 evaluation and cost governance · P6 governance, delivery, bonus.
Branches and commit counts are in section 4.

**What this check is based on.** It was written by reading `ref-doc.md`, the
files, the committed evidence and the git history. **No test or script was run
for this check.** It relies on results obtained earlier in the project, each
stated where used: `python scripts/verify_submission.py` (49 of 49 checks
passed, run at commit `6423964`), `python scripts/verify_citations.py` (all
citations and 26 controls resolve) and the full offline suite
(`pytest -q -m "not live"`: 236 passed, 1 live test deselected; run before the
last three documentation commits, which touched no code).

**About the marks.** `ref-doc.md` gives no rubric or weights (only "7 categories /
100 marks" and the grade bands). The mark table in section 1.2 is therefore a
count of ref-doc rows met, with equal weights assumed (plan.md A-1). It is not
the official score and contains no quality judgment.

---

## 1. Summary

### 1.1 Requirement coverage

| Area | Count | Done | Weakness or open |
|---|---|---|---|
| Acceptance criteria AC-01 to AC-12 (§5.1) | 12 | 12 | AC-01 to AC-04 rest on an evaluation run made *before* three fixes; see 5.1 |
| Non-functional NFR-01 to NFR-07 (§5.2) | 7 | 6 | **NFR-07 (PR merges) is pending:** you will do it at delivery; the marks in 1.2 assume it is done |
| §7 artifact rows (25) | 25 | 24 | The "Git workflow" row is the same pending item |
| §8 evidence-table rows | 10 | 10 | Weaknesses noted per row |
| §8.1 Good-to-have sub-items (3 bullets, 5 items) | 5 | 4 | **Optimization note (before/after) not done** |
| §6.2 out-of-scope items respected | 4 | 4 | none |

### 1.2 Mark summary: what we covered against the ref-doc, out of 100

**What the ref-doc gives and does not give.** `ref-doc.md` says the review uses
"the Hackathon Rubric (7 categories / 100 marks)" (§2, L24) and lists the grade
bands (L26). It does **not** publish the rubric, the weight of each category, or
how a row is scored. So no mark can be read straight from it. The table below
therefore uses **only counts of what the ref-doc lists**, with two stated
assumptions and **no quality judgment**:

1. The seven categories are the seven artifact groups §7.1 to §7.7 (plan.md A-1),
   **weighted equally** (100 / 7 = 14.29 each).
2. Inside a category every row counts equally. A row is **met** when its artifact
   exists at the path the ref-doc gives and contains what that row lists (checked
   by `scripts/verify_submission.py`, 49 of 49 checks, and by this document).

Marks in a category = (rows met / rows in the category) x 14.29.

| # | Category (ref-doc §7 group) | Rows the ref-doc lists | Rows met | Marks |
|---|---|---|---|---|
| 7.1 | Agentic system foundation (L140 to L144) | 5 | 5 | **14.29** |
| 7.2 | Observability and tracing (L150 to L153) | 4 | 4 | **14.29** |
| 7.3 | Performance and cost governance (L159, L160) | 2 | 2 | **14.29** |
| 7.4 | Security and guardrails (L166 to L168) | 3 | 3 | **14.29** |
| 7.5 | Governance and compliance (L174 to L177) | 4 | 4 | **14.29** |
| 7.6 | Agent evaluation and testing (L183 to L186) | 4 | 4 | **14.29** |
| 7.7 | Engineering and delivery (L192 to L194) | 3 | 3 if you do the PR merges; 2 today | **14.29** (9.52 today) |
| | **Total** | **25** | **25 with the PR merges; 24 today** | **100.0 with the PR merges; about 95.2 today** |

**The other counts in the ref-doc**

| ref-doc list | Items | Met |
|---|---|---|
| Acceptance criteria AC-01 to AC-12 (L88 to L99) | 12 | 12 |
| Non-functional NFR-01 to NFR-07 (L105 to L111) | 7 | 6 today; 7 with the PR merges (NFR-07) |
| §8 evidence-table rows (L204 to L213) | 10 | 10 |
| §6.2 out-of-scope items respected (L125 to L128) | 4 | 4 |
| §3.4 applicable rules (L56 to L60) | 5 | 5 |
| §8.1 good-to-have items (L217 to L219) | 5 | 4: the optimization note (L219) is not done |

**Reading it.**

- On the ref-doc's own lists, **every required row is met**. The only required
  item not done is the PR merges (L111, L193), which you will do; with them the
  coverage is 100%.
- The one listed item not done is the **optimization note (L219)**. It is a
  §8.1 good-to-have and is not one of the 25 rows above, so it is not in this
  total; it may earn extra credit if the rubric gives any, which the ref-doc
  does not say.
- **This is coverage, not quality.** If the real rubric also grades quality or
  depth (for example the accuracy figure), it cannot be known from `ref-doc.md`.
  The earlier deductions in this file for that were my judgment and have been
  removed.
- The ref-doc lists no band above Merit (75 to 89); a score over 89 is not
  described there.

**The golden-set size (30 cases) is enough.** AC-12 (L99), §7.6 (L183) and §8
(L212) ask only for "a golden set" and give no size. The file holds 47 authored
cases and 30 are scored, by team decision (plan.md, P5-03).

### 1.3 What is not covered, and optional items that carry no ref-doc requirement

**Not covered, by the ref-doc's own lists:**

| Item | ref-doc | Type | Status |
|---|---|---|---|
| Pull-request merges: at least 3 `--no-ff` merges, no direct pushes to `main` | L111 NFR-07, L193 | Mandatory | You will do it (`docs/delivery-runbook.md`) |
| Optimization note with a measured before/after latency or cost improvement | L219 | Good-to-have | Not done |

**Optional improvements (no ref-doc line requires them, so no marks are assigned to them here):**

- **Re-running the evaluation after the three fixes.** The ref-doc asks for a
  DeepEval report over a golden set (L99, L183, L212) and for root cause and fix
  per failure (L95). It never asks for a re-run or an improved accuracy. The
  committed report predates the fixes (accuracy 0.6) and says so.
- **Running `regenerate --traces --eval` once as one command.** NFR-02 and the
  Reproducibility Rule (L106, L60) ask that one documented command exist, and it
  does.
- **Closing the four encoded-payload red-team gaps.** The ref-doc asks for a
  small red-team set with results (L218), which we have.
- **Implementing the compliance gaps** (DPDP notice, consent, erasure; AI Act
  Art. 50(2)). The ref-doc asks for a mapping (L176), which we have.
- **The Phoenix screenshot cost column** reads $0 (no prices configured in
  Phoenix); the real estimate is in `reports/golden_signals.json`, and the README
  and model card explain the difference.

---

## 2. What was NOT covered (stated plainly)

| # | Item | Type | Status | Note |
|---|---|---|---|---|
| 1 | Pull-request merges: at least 3 `git merge --no-ff` merges, no direct pushes to `main` (§5.2 NFR-07, §7.7 Git workflow) | **Mandatory** | ⏳ Not done | `main` holds only the root commit. The merges are made on the Git host from the six phase branches (`docs/delivery-runbook.md`). Cannot be completed locally. |
| 2 | Optimization note with a measured before/after latency or cost improvement, two Phoenix-derived reports (§8.1) | Good-to-have | ❌ Not done | plan.md P5-11 to P5-15 deferred by decision. Not required for §7 marks. |
| 3 | Streamlit UI | Not in `ref-doc.md` | ✅ Built (optional extra) | See section 3. A live chat through UI and API was not run (needs Gemini calls). |
| 4 | Re-scoring the evaluation after the three fixes (FA-01 to FA-03) | Quality, not a row | ❌ Not done | `reports/eval_report.json` is the pre-fix run: accuracy 0.6. |
| 5 | Golden-set size | Not required (ref-doc sets no size) | ✅ Decided: 30 cases scored | The golden file holds 47 authored cases; the scored set is the first 30 by team decision (plan.md P5-03). `ref-doc.md` AC-12 and §7.6 ask only for "a golden set". The 17 not scored (out_of_scope 3, service_request 2, memory 4, prompt_injection 4, cross_customer_access 3, one more ambiguous) are extra data; those behaviours are evidenced by the red-team, the memory log and the tests. Not counted as a weakness. |
| 6 | Running `regenerate --traces --eval` as one invocation | Mandatory command (NFR-02) | ⚠️ Not exercised as one run | The command exists and is documented; its two halves were run separately (`regenerate --traces --commit-evidence`, `eval --limit 30`). |
| 7 | Phoenix dashboard cost column | §7.3 | ✅ Explained | Phoenix shows $0 (no model prices configured there); the real estimate ($0.4398 at list price) is in `reports/golden_signals.json`. The README and model card now explain the $0 (commit `b35b8f5`); the screenshot itself is unchanged. |
| 8 | FA-03's fix commit not cited in `docs/failure-analysis.md` | Quality | ✅ Fixed | The doc now cites commit `6d013f2`, and each failure also cites its Phoenix trace_id and span_id (commit `87727cc`). |
| 9 | `reports/eval_report.json` is a copy of `reports/eval_report_initial.json` | Quality | ⚠️ | Same content, committed at both paths (commit `958ff8f`) so the canonical path exists. |
| 10 | Red-team: 4 encoded-payload attacks not detected (base64, leetspeak, zero-width, underscore-joined) | Documented gap | ⚠️ | Counted as accepted in `reports/redteam_results.json`. |
| 11 | Compliance gaps: DPDP notice, consent, access, correction, erasure, retention, breach notification; AI Act Art. 50(2); NIST fairness and feedback loop | Not required to implement | ⚠️ Documented | `docs/compliance.md` section 4 and `docs/security-approach.md`. |
| 12 | Real authentication and secrets rotation | Out of scope (§6.2), "document the approach" | ✅ Documented only | `docs/security-approach.md`. |
| 13 | `guardrails-ai` was pinned in `requirements.txt` but no code imports it | §4 / §8 allow "Guardrails-AI / LLM Guard validators (or policy functions)" | ✅ Fixed | The pin is removed (commit `9e538c6`); guards are policy functions plus Presidio, as the architecture doc now states. |
| 14 | `openai`, `anthropic`, `litellm` are installed in the environment | §3.4 Gemini-only | ⚠️ Transitive only | Pulled in by `deepeval` (and by `guardrails-ai`, which is no longer pinned but remains in the local environment). Not listed in `requirements.txt`, and no code in `src/`, `scripts/`, `tests/` or `mcp_server/` imports them. DeepEval's default OpenAI judge is replaced by a Gemini judge. |
| 15 | Fresh-clone reproducibility script (plan.md P6-15/16) | Not in ref-doc | ➖ Skipped by decision | Not required by §7 or §8. |
| 16 | `pip check` reports one unrelated conflict (huggingface-hub wants click >= 8.4.2, 8.3.3 installed) | Environment | ⚠️ Pre-existing | Not touched. |
| 17 | Optional screenshot of the API demo (M-6) | Optional | ➖ Not taken | The demo log exists: `logs/api_demo.log`. |

**Classification.** *Mandatory* = the §7 rows, the acceptance criteria and the
NFRs. *Good-to-have* = §8.1 and the FastAPI bonus. *Not evaluated* (§2) =
interface visual polish, generic unit-test volume, deployment path.

---

## 3. Streamlit UI (built, optional extra)

Not in `ref-doc.md`. A simple chat page exists in `src/ui/` (commits `8018cc1`,
`7e6f9e5`, `45d4b38`): `python -m src.api` in one terminal, `python -m src.ui` in
another.

- **Not required, not scored.** §2 says visual polish of any interface is not
  evaluated; §4 lists the interface layer as "CLI (required) . FastAPI streaming
  (optional / bonus)". Streamlit is not in §4's tool table: it is recorded as an
  optional extra (`plan.md`, `README.md`).
- **Controls kept.** It is a thin client of `POST /chat/stream` and never imports
  the graph, so the input guard, output guard, risk gate, tool-scope gateway and
  audit trail apply unchanged. It shows the AI disclosure at the top from the
  first render (CTL-26), shows node names only while a turn runs (never unguarded
  node content), and masks the answer again.
- **Tests, all offline:** `tests/test_ui_client.py` (12) and `tests/test_ui_app.py`
  (13) pass; the real Streamlit server was booted once (healthy, HTTP 200,
  loopback only).
- **Not done:** a live chat through the UI and the API (needs Gemini calls). No
  authentication: the customer picked is trusted, for local use only.

---

## 4. Phases and what each delivered

| Phase | Branch | Commits | Delivered | Key proof |
|---|---|---|---|---|
| 0 | `main` | 1 | Root commit: `ref-doc.md`, `plan.md`, `.gitignore` | `git log main` |
| 1 | `phase-1/foundation-graph-mcp` | 26 | Synthetic data, MCP server, LangGraph graph, CLI, first tests | `logs/mcp_transcript.jsonl`, `data/synthetic/` |
| 2 | `phase-2/context-memory-rag` | 18 | Context engineering, tiered memory, agentic RAG | `logs/memory_test.log`, `data/policy_corpus/` |
| 3 | `phase-3/observability-tracing` | 16 | Phoenix tracing, tool log, trace export | `traces/phoenix_spans.parquet`, `logs/tool_calls.jsonl` |
| 4 | `phase-4/security-guardrails-audit` | 18 | Guardrails, audit trail, Presidio, red-team, scanners | `logs/agent_actions.jsonl`, `reports/redteam_results.json` |
| 5 | `phase-5/evaluation-cost-governance` | 30 | DeepEval harness, golden signals and cost, failure analysis, dashboard | `reports/eval_report.json`, `reports/golden_signals.json`, `docs/failure-analysis.md` |
| 6 | `phase-6/governance-delivery-bonus` | 27 | Governance pack, streaming API bonus, verifiers, delivery runbook | `docs/`, `reports/evidence_manifest.json` |

136 commits in total, each with one teammate as author and the other as the
final `Co-authored-by:` trailer; authors alternate.

---

## 5. Line-by-line check

### 5.0 §1 Project identity and §2 Engagement overview

| ref-doc item | Status | Proof |
|---|---|---|
| §1 Business case BC-AAIE-HACK-01, banking retail servicing | ✅ | README title and `docs/model-card.md` |
| §2 Duration 20 hours | ➖ | Not verifiable from the repository |
| §2 Team of 2 to 4 | ✅ | 2 people (Kaajal Krishnamurthy, Akash Saranathan) |
| §2 Evaluation from committed evidence only, no live demo | ✅ | All evidence committed; `reports/evidence_manifest.json` lists 40 artifacts with sha256 |
| §2 "What is not evaluated": visual polish, unit-test volume, deployment path | ✅ | No polished UI (only a simple optional Streamlit page), no Docker; the tests are not claimed as a metric |

### 5.1 §3 Problem, expected solution and rules

**§3.3 "Expected solution" bullets**

| Bullet | Status | Proof | Phase |
|---|---|---|---|
| LangGraph graph: typed state, supervisor, specialised workers (intake, account-servicing, dispute, product-info), conditional routing, checkpointing, structured output | ✅ | `src/graph.py`, `src/state.py` (`CopilotState`), `src/schemas.py` (`RouteDecision`), `src/agents/`; `AsyncSqliteSaver` in `open_checkpointer`; routes in `route_from_supervisor` and `route_after_input_guard` | P1 |
| Custom MCP server, at least 2 tools and 1 resource, consumed via langchain-mcp-adapters | ✅ | `mcp_server/server.py`: 7 tools, 1 resource (`bank://reference/dispute-windows`); `src/mcp_client.py`; `logs/mcp_transcript.jsonl` (52 records, includes a `resources/read`) | P1 (7th tool P2) |
| Engineered context: write / select / compress / isolate, summarization, quarantine of untrusted text | ✅ | `src/context/` (`write.py`, `select.py`, `compress.py`, `isolate.py`, `summarization.py`, `quarantine.py`); `docs/architecture.md` section 7 | P2 |
| Tiered memory with verified cross-session persistence | ✅ | `src/memory/`; `tests/test_memory_persistence.py`; `logs/memory_test.log` ends `PASS: cross-session recall verified with real Gemini + LangMem` | P2 |
| Agentic-RAG tool over a banking-policy corpus | ✅ | `src/tools/rag_tool.py` (compiled retrieve, grade, rewrite, answer or abstain subgraph); 12 documents in `data/policy_corpus/` | P2 |
| Phoenix instrumentation, committed trace export, machine-generated tool log, evidence-linked failure analysis | ✅ | `src/observability/tracing.py`; `traces/phoenix_spans.parquet`; `logs/tool_calls.jsonl`; `docs/failure-analysis.md` | P3, P5 |
| Golden-signals report and cost/latency dashboard | ✅ | `reports/golden_signals.json`; `reports/dashboard.png`, `reports/dashboard_data.csv` | P5 |
| Input/output guardrails, audit trail, secrets hygiene | ✅ | `src/guardrails/`; `logs/agent_actions.jsonl`; `.env.example`, `.gitignore`, `reports/secrets_scan.json` | P4 |
| Governance pack: risk register, model/system card, compliance mapping, output-risk classification | ✅ | `docs/risk-register.md`, `docs/model-card.md`, `docs/compliance.md`, `docs/output-risk.md` | P6 |
| Agent-level evaluation (LLM-as-judge + hallucination) and agent tests (routing, loop/cascade guard, tool-contract) | ✅ | `reports/eval_report.json`, `tests/test_routing.py`, `tests/test_loops.py`, `tests/test_tool_contracts.py`. Eval is the pre-fix run | P5 (tests P1/P2) |
| Reproducible local-run runbook | ✅ | `README.md` sections "The two commands" and "Regenerate traces and the evaluation" | P1 to P6 |

**§3.4 Applicable rules**

| Rule | Status | Proof and note |
|---|---|---|
| Evidence-in-Repo: only committed artifacts count; each must have producing code | ✅ | `reports/evidence_manifest.json` records the producing command for each artifact; README table "Where each required artifact comes from". Manual/hand-written items are labelled: `reports/dashboard.png` (screenshot), `docs/failure-analysis.md` (written from traces) |
| Citation-Resolves: every cited run/span id, log record or control file resolves | ✅ | `scripts/verify_citations.py`; `reports/citation_check.json`: 6 docs and 26 controls resolve. Tested in `tests/test_verify_citations.py` |
| Synthetic-Data: only synthetic data; numbers masked, never logged in plaintext | ✅ | `scripts/generate_synthetic_data.py --seed 42`; `src/common/masking.py`; `reports/pii_scan.json` 0 findings (scanner fixed in P6 for hex-id false positives) |
| Open-Source and Gemini-Only: Gemini is the only provider | ✅ | Models: `gemini-3.5-flash` (default), `gemini-3.5-flash-lite` (fast), eval ran on `gemini-3.1-flash-lite` (`reports/eval_report.json` metadata). No code imports another provider; `openai`, `anthropic`, `litellm` are transitive installs only (item 14 in section 2) |
| Reproducibility: regenerable from a single documented command with committed sample inputs | ✅ | `python -m src.cli regenerate --traces --eval` documented; sample inputs `data/sample_inputs/conversations.jsonl` (14 conversations, 15 turns) and `data/golden_set/golden.jsonl` (47 authored cases, 30 scored). Not exercised as one combined run (item 6) |

### 5.2 §4 Technology and framework stack

| Layer | Approved tool | Used | Status | Proof |
|---|---|---|---|---|
| Language / agent framework | Python 3.11+, LangGraph | Python 3.12, langgraph 1.2.11 | ✅ | `requirements.txt`, `docs/architecture.md` section 4 |
| LLM provider | Gemini only | langchain-google-genai 4.4.0 | ✅ | `src/llm.py` |
| Interoperability | MCP Python SDK (stdio) + langchain-mcp-adapters | mcp 1.30.0, adapters 0.3.2 | ✅ | `mcp_server/server.py`, `src/mcp_client.py` |
| Memory | langgraph-checkpoint-sqlite + LangMem | 3.1.1, 0.0.30 | ✅ | `src/memory/` |
| Retrieval | Chroma or FAISS + Sentence-Transformers | Chroma 1.5.9, all-MiniLM-L6-v2 | ✅ | `src/tools/rag_index.py` |
| Observability (mandated) | Arize Phoenix + OpenTelemetry / openinference | arize-phoenix 14.6.0, local in-process | ✅ | `src/observability/tracing.py` |
| Evaluation | DeepEval (judge = Gemini) + pytest | deepeval 4.2.3, custom Gemini judge | ✅ | `src/evaluation/gemini_judge.py` |
| Security | Guardrails-AI / LLM Guard, Presidio, python-dotenv | Presidio + policy functions, python-dotenv | ✅ | `src/guardrails/pii.py`; guards are policy functions plus Presidio (allowed by §8); the unused `guardrails-ai` pin was removed |
| Interface | CLI (required), FastAPI streaming (optional) | Both, plus a simple optional Streamlit page | ✅ | `src/cli.py`, `src/api/`, `src/ui/` |

### 5.3 §5.1 Functional acceptance criteria

The evaluation numbers below come from `reports/eval_report.json`: 30 cases,
accuracy 0.6 (18 of 30), run **before** the FA-01 to FA-03 fixes.

| ID | Criterion (short) | Status | Proof and where | Phase | Weakness |
|---|---|---|---|---|---|
| AC-01 | Account info (balance, transactions, statement) accurate and grounded in tool data | ✅ | Balance answer "3,023.36 USD" equals the tool result in `logs/mcp_transcript.jsonl` (`get_account_balance`); output-risk sample case g-bal-001 in `reports/output_risk_sample.json`; eval: account_balance 3 of 3, account_statement 2 of 2, account_transactions 1 of 3 | P1 (masking P4) | Two transaction cases were misrouted to the dispute worker (FA-01); fixed but not re-scored |
| AC-02 | Dispute: capture, eligibility check against policy, draft or next step for a human | ✅ | `src/agents/dispute.py`; tool `check_dispute_eligibility` + resource `bank://reference/dispute-windows`; `create_dispute_case` is draft-only (CTL-25); eval: dispute_intake 3 of 3; answers always gated (`reports/output_risk_sample.json`, 25 of 25 high-tier gated) | P1 capture, P2 eligibility | dispute_eligibility 0 of 1 and dispute_status 0 of 1 in the pre-fix eval (FA-01, FA-02 fixed later) |
| AC-03 | Policy question answered from the corpus with a citation; abstains when unsupported | ✅ | `src/tools/rag_tool.py`; eval answers cite `POL-*` sections (for example g-abs-002); abstention g-abs-001 correct; `data/policy_corpus/` deliberately lacks mortgages, crypto | P2 | Eval: policy_question 6 of 12, abstention 2 of 3. Two questions abstained although a document exists (g-pol-010, g-pol-011) and their cause is not investigated (`docs/model-card.md` section 8) |
| AC-04 | Intent identified; ambiguous or out-of-scope requests clarified or escalated | ✅ | `src/agents/supervisor.py`, `intake.py`, `escalate.py`; `tests/test_routing.py` (4 tests); eval ambiguous 1 of 2; escalations in `logs/agent_actions.jsonl` | P1, P2, P4 | Out-of-scope cases are not among the 30 scored; g-amb-001 hit the recursion fallback |
| AC-05 | Uses facts from earlier in the conversation and recalls prior-session context | ✅ | `logs/memory_test.log`: session 1 states an email preference, a new session recalls it (`PASS`); `tests/test_memory_persistence.py` | P2 | Memory categories are not among the 30 scored eval cases |
| AC-06 | Injection and other-customer access refused; account/card numbers never exposed in answers or logs | ✅ | `reports/redteam_results.json` and `docs/redteam-results.md`: 37 of 37 attacks passed, 4 documented known gaps; `src/tools/gateway.py` (CTL-05) with `tests/test_tool_gateway.py`; input guard block records in `logs/agent_actions.jsonl`; `reports/pii_scan.json`: 0 findings | P4 | Injection detection is literal-pattern based (encoded payloads evade it) |
| AC-07 | Machine-generated tool log `logs/tool_calls.jsonl`; tool names reconcile with the code | ✅ | `logs/tool_calls.jsonl` (81 records, all of timestamp, agent, tool_name, args, result, latency_ms, status); `src/observability/tool_logging.py`, `src/tools/registry.py`; `reports/tool_reconciliation.json` (8 of 8 tools reconcile) | P3 | none |
| AC-08 | `docs/failure-analysis.md`: at least 3 real failures, each citing Phoenix run_id plus span_id or a tool-log record, with root cause and fix | ✅ | `docs/failure-analysis.md`: FA-01, FA-02, FA-03, each with a real `run_id`, log records, root cause and fix; every citation resolves (`reports/citation_check.json`) | P5 | none: each failure cites run_id, trace_id and span_id, and FA-03 cites its fix commit `6d013f2` (commit `87727cc`) |
| AC-09 | Golden-signals report (latency by thinking/acting/tool, tokens, cost estimate, accuracy, hallucination rate) and a cost/latency dashboard (screenshot and data file) | ✅ | `reports/golden_signals.json`: thinking p50 693 ms / p95 7,452 ms, acting 15 / 9,413, tool 3,573 / 20,181; tokens 566,547 in / 97,826 out; cost $0.4398 at list price (`src/observability/pricing.py`, source URL and date recorded); accuracy 0.6; hallucination rate 0.0. `reports/dashboard.png` (Phoenix project page: 773 traces, latency, tokens, cost columns) and `reports/dashboard_data.csv` (6,810 spans) | P5 | Phoenix's own cost shows $0 (explained in the README and model card); the runs used the free tier, so $0.4398 is a list-price equivalent, stated as such; accuracy is pre-fix |
| AC-10 | Input/output guardrails wired into the agent's I/O path; machine-generated audit trail `logs/agent_actions.jsonl` | ✅ | `src/graph.py` (`input_guard` node first, output guard and risk gate in `finalize_node`); `src/guardrails/`; `logs/agent_actions.jsonl` (86 records with actor, action, tool, decision, timestamp) | P4 | none |
| AC-11 | Governance pack: risk register, model/system card, compliance mapping (EU AI Act / NIST AI RMF / DPDP), output-risk classification, each citing a committed control | ✅ | `docs/risk-register.md` (17 risks), `docs/model-card.md`, `docs/compliance.md`, `docs/output-risk.md`; `docs/control-catalog.md` (26 controls); citations verified by `scripts/verify_citations.py` | P6 (catalog P5) | Compliance gaps are documented, not implemented |
| AC-12 | Agent evaluation: DeepEval report over a golden set (hallucination plus faithfulness/relevance) and agent tests (routing, loop/cascade guard, tool contract) | ✅ | `reports/eval_report.json` (DeepEval, Gemini judge: hallucination rate 0.0, faithfulness mean 0.982, answer relevancy mean 0.742, accuracy 0.6); `src/evaluation/harness.py`; `tests/test_routing.py` (4), `tests/test_loops.py` (4), `tests/test_tool_contracts.py` (13); 236 offline tests passed | P5 (tests P1, P2) | Pre-fix run; report is a copy of the initial run |

### 5.4 §5.2 Non-functional requirements

| ID | Requirement | Status | Proof and where | Phase |
|---|---|---|---|---|
| NFR-01 | No secrets committed; env-var config, committed `.env.example`, `.gitignore` covers `.env` | ✅ | `.env.example` (placeholders), `.gitignore` (`.env`, `.env.*`), `reports/secrets_scan.json` (tree and full history clean), `scripts/check_secrets.py` | P1, P4 |
| NFR-02 | Single documented command runs the copilot; a second regenerates traces and evaluation; committed sample inputs | ✅ | README "The two commands": `python -m src.cli chat --customer-id C0001` and `python -m src.cli regenerate --traces --eval`; sample inputs committed | P1, P3, P5, P6 |
| NFR-03 | Untrusted free text quarantined, never treated as instructions | ✅ | `src/context/quarantine.py` (CTL-06): delimiter plus schema-constrained extraction; input guard and red-team | P2, P4 |
| NFR-04 | Async where tools and models are called; graceful degradation (timeouts, retries, exit conditions) | ✅ | `async` nodes and `ainvoke`; `src/llm.py` backoff (CTL-13); `src/tools/resilience.py` (CTL-12); step and recursion guards (CTL-14, CTL-15); `tests/test_loops.py`, `tests/test_cli_recursion_guard.py` | P1, P3 |
| NFR-05 | All data synthetic; PANs and account numbers masked and never logged in plaintext | ✅ | `data/synthetic/`; `src/common/masking.py`; `src/guardrails/ingress.py`; `reports/pii_scan.json` 0 findings over `logs/`, `traces/`, `reports/`, `docs/` | P1, P4 |
| NFR-06 | Evidence artifacts machine-generated by committed code, with the code committed alongside | ✅ | Producing commands in `reports/evidence_manifest.json` and the README table | P3 to P6 |
| NFR-07 | PR-driven Git history: at least 3 PR merges (`git merge --no-ff`), no direct pushes to `main` | ⏳ | **Not done.** Six stacked phase branches are ready; `main` has only the root commit. Steps: `docs/delivery-runbook.md`. After the merges run `python scripts/verify_submission.py --check-git-merges` | Delivery |

### 5.5 §6 Functional scope

| Item | Status | Proof |
|---|---|---|
| §6.1 The copilot plus observability, cost governance, security, governance and evaluation | ✅ | Sections 5.1 to 5.3 |
| §6.1 Phoenix tracing, golden signals and cost/latency governance, guardrails, audit, secrets hygiene, governance docs, agent evaluation and tests | ✅ | Section 5.6 |
| §6.1 A CLI to drive requests and to regenerate traces and the evaluation | ✅ | `src/cli.py` commands `chat`, `run`, `mcp-demo`, `regenerate`, `eval`, `export`, `redteam` |
| §6.2 No Docker, Rancher, k8s or cloud deployment | ✅ | `verify_submission.py` check "no Docker/compose files": none tracked |
| §6.2 No real core-banking connectivity or real data | ✅ | Synthetic generator and MCP server over local JSON |
| §6.2 No front-end polish, no generic test volume for its own sake | ✅ | No polished UI (a simple optional Streamlit page exists); tests target agent behaviour |
| §6.2 OAuth and secrets rotation documented, not built | ✅ | `docs/security-approach.md` |

### 5.6 §7 Required artifacts, row by row

Every path was confirmed present and non-empty by `verify_submission.py`.

**7.1 Agentic system: foundation**

| Row | Path | Status | Contains and proof | Phase |
|---|---|---|---|---|
| LangGraph graph | `src/graph.py` | ✅ | Typed state (`src/state.py`), supervisor plus 4 workers plus escalation node, conditional edges, checkpointer, structured output (`src/schemas.py`) | P1 (guards P4) |
| MCP server | `mcp_server/`, `logs/mcp_transcript.jsonl` | ✅ | 7 tools, 1 resource; consumed via langchain-mcp-adapters; 52-record transcript | P1 |
| Context engineering | `src/context/` | ✅ | Write, select, compress, isolate, summarization, quarantine | P2 |
| Tiered memory | `src/memory/`, `tests/test_memory_persistence.py`, `logs/memory_test.log` | ✅ | Short-term (checkpointer) plus long-term (LangMem, SQLite); recall test with committed PASS log | P2 |
| Agentic-RAG tool | `src/tools/rag_tool.py`, `data/policy_corpus/` | ✅ | Retrieval-in-the-loop subgraph over 12 synthetic policy documents | P2 |

**7.2 Observability and tracing**

| Row | Path | Status | Contains and proof | Phase |
|---|---|---|---|---|
| Phoenix instrumentation | `src/observability/tracing.py` | ✅ | `init_tracing` called on the run path in `src/cli.py` (chat, run, mcp-demo, API lifespan) | P3 |
| Trace export | `traces/phoenix_spans.parquet` | ✅ | 6,810 spans, 44 distinct names, supervisor plus at least 3 workers plus every logged tool, non-null latencies, run_id present (`verify_submission.py`) | P3, re-exported P5 |
| Tool-invocation log | `logs/tool_calls.jsonl` | ✅ | 81 records with all required fields; names reconcile | P3 |
| Failure-mode analysis | `docs/failure-analysis.md` | ✅ | FA-01 to FA-03, each with run_id, trace_id, span_id, root cause and fix commit | P5 |

**7.3 Performance and cost governance**

| Row | Path | Status | Contains and proof | Phase |
|---|---|---|---|---|
| Golden-signals report + producing script | `reports/golden_signals.json`, `src/observability/golden_signals.py` | ✅ | p50/p95 by thinking/acting/tool, tokens in/out, cost $0.4398, accuracy and hallucination rate imported from the eval; prices and source URL in `src/observability/pricing.py` | P5 |
| Cost/latency dashboard | `reports/dashboard.png`, `reports/dashboard_data.csv` | ✅ | Screenshot of the local Phoenix project page and the 6,810-span export it was drawn from. Note: Phoenix's cost column reads $0 (no prices configured there); explained in the README and model card | P5 |

**7.4 Security and guardrails**

| Row | Path | Status | Contains and proof | Phase |
|---|---|---|---|---|
| Guardrail code | `src/guardrails/` | ✅ | Ingress masking, injection and cross-customer detection, output guard, output-risk gate, audit; wired in `src/graph.py` | P4 |
| Audit trail | `logs/agent_actions.jsonl` | ✅ | 86 records; actor, action, tool, decision, timestamp on each | P4 |
| Secrets hygiene | `.env.example`, `.gitignore` | ✅ | Placeholders only; `.env` ignored; scan clean | P1, P4 |

**7.5 Governance and compliance (citation-gated)**

| Row | Path | Status | Contains and proof | Phase |
|---|---|---|---|---|
| Risk register | `docs/risk-register.md` | ✅ | 17 risks: category (OWASP LLM / NIST AI RMF), likelihood, impact, mitigation citing CTL ids, residual risk, owner | P6 |
| Model / system card | `docs/model-card.md` | ✅ | Gemini model ids, synthetic data, intended use, limitations, known failure modes citing FA-xx, out-of-scope, evaluation summary | P6 |
| Compliance mapping | `docs/compliance.md` | ✅ | EU AI Act, NIST AI RMF, DPDP: obligation, how addressed, evidence; article and section numbers checked against the official texts on 2026-09-19 | P6 |
| Output-risk classification | `docs/output-risk.md` | ✅ | Low/medium/high tiers, how high-risk is gated, a sample from real runs (`reports/output_risk_sample.json`); code from P4 | P6 (code P4) |

**7.6 Agent evaluation and testing**

| Row | Path | Status | Contains and proof | Phase |
|---|---|---|---|---|
| Evaluation report + harness | `reports/eval_report.json`, `src/evaluation/harness.py` | ✅ | DeepEval over the golden set (30 cases): hallucination, faithfulness, relevancy; Gemini judge (`src/evaluation/gemini_judge.py`). Note: the run predates the three fixes (accuracy 0.6); `ref-doc.md` does not ask for a re-run | P5 |
| Routing-logic test | `tests/test_routing.py` | ✅ | 4 tests asserting conditional-edge routing | P1 |
| Loop/cascade guard | `tests/test_loops.py` | ✅ | 4 tests asserting the step and recursion limits stop runaway loops | P1 |
| Tool-contract test | `tests/test_tool_contracts.py` | ✅ | 14 tests: a parametrized input-schema test over the MCP tools; output-shape tests for balance, transactions, statement, create-dispute (draft-only), service request, eligibility and dispute status; four error-path tests (unknown dispute, invalid service-request type, dispute on a foreign transaction, bad eligibility reason); `policy_search` input/output schema and its abstention path. | P1, extended P2 |

**7.7 Engineering and delivery**

| Row | Path | Status | Contains and proof | Phase |
|---|---|---|---|---|
| Local-run runbook | `README.md` | ✅ | Single-command run, regeneration of traces and eval, committed sample inputs, artifact-to-command table | P1 to P6 |
| Git workflow | git history | ⏳ | Six phase branches ready and every commit carries both teammates; **the at least 3 `--no-ff` PR merges are not done** (NFR-07) | Delivery |
| Bonus | `src/api/` | ✅ | Async FastAPI streaming (`POST /chat/stream`, `GET /health`), 25 tests, `scripts/demo_api.py`, `logs/api_demo.log`. A backend endpoint, not a UI | P6 |

### 5.7 §8 Evidence production table

| Artifact | Format required | Status | How ours was produced | Note |
|---|---|---|---|---|
| Phoenix trace export | Parquet or JSONL of OTel spans, exported from Phoenix | ✅ | `python -m src.cli export --parquet traces/phoenix_spans.parquet` | ref-doc's `px.Client()` does not exist in the pinned arize-phoenix 14.6.0; the real client API (`phoenix.client.Client`) is used and noted in the README |
| Tool-invocation log | JSONL, one object per call, from a logging wrapper | ✅ | `src/observability/tool_logging.py` via `src/tools/registry.py` | |
| Failure-mode analysis | Markdown, at least 3 real failures | ✅ | Written from real runs; checked by `verify_citations.py` | See AC-08 notes |
| Golden-signals report | JSON from a script reading Phoenix spans | ✅ | `python -m src.observability.golden_signals --eval reports/eval_report_initial.json --out reports/golden_signals.json` | Cost = tokens times published price |
| Cost/latency dashboard | PNG plus CSV | ✅ | Screenshot of Phoenix UI; `python -m src.cli export --csv reports/dashboard_data.csv` | Phoenix cost shows $0 (explained in the README and model card) |
| Guardrail code | Python module wired into I/O nodes | ✅ | `src/guardrails/`, wired in `src/graph.py` | Policy functions plus Presidio |
| Audit trail | JSONL from audit middleware | ✅ | `src/guardrails/audit.py` (`record_action`) | |
| Governance pack | Four Markdown docs, each entry citing a control | ✅ | Hand-written; checked by `verify_citations.py` | |
| Evaluation report | JSON from a DeepEval run plus its harness | ✅ | `python -m src.cli eval --limit 30 --out reports/eval_report_initial.json`, committed also as `reports/eval_report.json` | Pre-fix run |
| Agent tests | Three pytest files | ✅ | Present, 21 tests between them | |

**§8.1 Good-to-have**

| Item | Status | Proof |
|---|---|---|
| FastAPI streaming endpoint | ✅ | `src/api/` (`app.py`, `streaming.py`, `__main__.py`), 25 tests in `tests/test_api.py` |
| A demonstrated local run (screenshot or log) | ✅ | `logs/api_demo.log`: a real answer streamed with arrival offsets and a blocked injection. Log only, no screenshot |
| PII-redaction middleware (Presidio) with a before/after sample | ✅ | `src/guardrails/pii.py`, `src/guardrails/ingress.py`; `reports/pii_redaction_sample.json` |
| A small red-team attack set and results | ✅ | `data/redteam/attacks.jsonl` (37 attacks, 8 categories); `reports/redteam_results.json`, `docs/redteam-results.md` |
| Optimization note with a measured before/after latency or cost improvement (two Phoenix-derived reports) | ❌ | **Not done** (plan.md P5-11 to P5-15 deferred) |

---

## 6. Quality caveats a reviewer could raise

1. **The evaluation predates the fixes.** Accuracy 0.6 was measured before FA-01 to FA-03 were fixed and has not been re-scored. `docs/model-card.md` and `docs/output-risk.md` say so plainly.
2. **Four eval mismatches are unexplained** (g-pol-010, g-pol-011 over-abstention; g-abs-002 answered where the label says abstain; g-amb-001 fallback). Listed in `docs/model-card.md` section 8, not investigated.
3. **Span error rate 12.0%** (816 of 6,820 spans) in `reports/golden_signals.json`, from free-tier quota errors and the failures documented in FA-01 to FA-03; the split was not measured.
4. **The golden signals cover the whole Phoenix history**, including failed runs (deliberately, so failures are visible), not one clean run. It has 6,820 spans, while the committed export has 6,810.
5. **Human review is a flag, not a workflow.** No review queue exists (`docs/output-risk.md` section 2).
6. **Authentication is not implemented.** The CLI and API trust `customer_id` (`docs/security-approach.md`).
7. **The manifest must be regenerated last** if any file it lists changes (`reports/evidence_manifest.json` was regenerated at commit `6423964`).

---

## 7. How to re-verify (not run for this check)

```bash
pytest -q -m "not live"                        # offline suite (236 tests at last run)
python scripts/verify_submission.py            # every section 7 row; add --check-git-merges after the PR merges
python scripts/verify_citations.py             # citations and the 26 controls
python scripts/check_secrets.py                # secrets in tree and history
python scripts/scan_evidence_for_pii.py        # plaintext PAN or account numbers in evidence
git log --oneline -- ref-doc.md                # exactly one commit
git log --first-parent --oneline main          # after delivery: root plus 6 merges
```

---

## 8. Annex A: line-by-line trace of `ref-doc.md`

Every requirement-bearing line of `ref-doc.md` (the `L` numbers are its own
line numbers), in order. Where a row is covered in more detail above, the
proof is repeated here in short so this annex stands alone. "Phase" is the
phase that delivered it (P1 to P6, section 4).

### A.1 Title and section 1 (identity), lines 1 to 14

| L | ref-doc says | Status | Proof and where | Phase |
|---|---|---|---|---|
| 1, 3 | Title; cross-cutting finale of seven areas: agentic core, context engineering, MCP, observability, cost governance, security and governance, agent evaluation | ✅ | Each area has a phase and artifacts: sections 4 and 5.6 | P1 to P6 |
| 11 | Business case title | ✅ | `README.md` line 1 | P1 |
| 12 | Business case ID BC-AAIE-HACK-01 | ✅ | `README.md` line 3 | P1 |
| 13, 14 | Domain (retail servicing), project type | ➖ | Descriptive | |

### A.2 Section 2 (engagement), lines 18 to 30

| L | ref-doc says | Status | Proof and where | Phase |
|---|---|---|---|---|
| 22 | Duration 20 hours | ➖ | Not verifiable from the repository | |
| 23 | Team of 2 to 4 | ✅ | 2 people; both credited on every commit | All |
| 24 | Automated review of the Git repository; 7 categories, 100 marks; scored from committed evidence; no live demo | ✅ | All evidence committed; `reports/evidence_manifest.json`. The rubric itself is not in `ref-doc.md` (section 0) | P6 |
| 25 | Review output is an Excel report | ➖ | Produced by the reviewer | |
| 26 | Grade bands Merit 75 to 89, Pass 60 to 74, below 60 not passed | ➖ | See the estimate in section 1.2 | |
| 28 | Evaluated: a working LangGraph multi-agent system with context engineering, tiered memory, custom MCP server, agentic RAG | ✅ | Section 5.6, 7.1 | P1, P2 |
| 28 | ...instrumented and governed: Phoenix observability | ✅ | `src/observability/tracing.py`, `traces/phoenix_spans.parquet` | P3 |
| 28 | ...cost and latency governance | ✅ | Measured and reported (`reports/golden_signals.json`); no runtime budget cap or per-request cost enforcement exists | P5 |
| 28 | ...guardrails and audit | ✅ | `src/guardrails/`, `logs/agent_actions.jsonl` | P4 |
| 28 | ...governance / compliance documentation | ✅ | `docs/risk-register.md`, `model-card.md`, `compliance.md`, `output-risk.md` | P6 |
| 28 | ...agent-level evaluation and testing | ✅ | `reports/eval_report.json` (pre-fix), three agent test files | P5 |
| 28 | Every claim is scored from committed evidence | ✅ | Manifest lists producing command and hash per artifact | P6 |
| 30 | Not evaluated: interface polish, generic unit-test volume, deployment path | ✅ | No polished UI (only a simple optional Streamlit page), no Docker; nothing claims test volume as a metric | |

### A.3 Section 3.1 Problem, line 38

| L | ref-doc says | Status | Proof and where | Phase |
|---|---|---|---|---|
| 38 | Resolve everyday requests end to end: balance and transaction queries | ✅ | AC-01; `get_account_balance`, `list_recent_transactions`, `get_statement_summary` in `mcp_server/server.py` | P1 |
| 38 | ...disputed-transaction intake | ✅ | AC-02; `src/agents/dispute.py`, `create_dispute_case` (draft only) | P1, P2 |
| 38 | ...product and fee questions | ✅ | AC-03; `src/agents/product_info.py`, `src/tools/rag_tool.py` | P2 |
| 38 | ...simple service requests | ✅ | `submit_service_request` (7th tool group); called 5 times in `logs/tool_calls.jsonl`; sample `conv-service` in `data/sample_inputs/conversations.jsonl`; output-shape and invalid-type tests in `tests/test_tool_contracts.py` | P1 |
| 38 | ...by understanding intent, calling the right tools | ✅ | Supervisor (`src/agents/supervisor.py`), `tests/test_routing.py` | P1 |
| 38 | ...grounding answers in policy | ✅ | Agentic RAG with citations and abstention | P2 |
| 38 | ...remembering context across the conversation | ✅ | Checkpointer plus LangMem; `logs/memory_test.log` | P2 |
| 38 | Production-ready: fully traced | ✅ | 6,810-span export; every tool call has a span (`verify_submission.py`) | P3 |
| 38 | ...cost- and latency-governed | ✅ | Golden signals, dashboard, tool timeouts and step limits; no cost budget enforcement | P5, P1 |
| 38 | ...guardrailed against injection and PII leakage | ✅ | `src/guardrails/`; 37-attack red-team; `reports/pii_scan.json` 0 findings | P4 |
| 38 | ...auditable | ✅ | `logs/agent_actions.jsonl` (86 records) | P4 |
| 38 | ...governed for compliance | ✅ | `docs/compliance.md`, `docs/control-catalog.md` | P6 |
| 38 | ...continuously evaluated | ⚠️ | Harness and `regenerate --eval` exist; no scheduled or CI evaluation, and the committed run is pre-fix | P5 |

### A.4 Section 3.2 Role, line 42

| L | ref-doc says | Status | Proof and where | Phase |
|---|---|---|---|---|
| 42 | Build a LangGraph multi-agent copilot | ✅ | `src/graph.py` | P1 |
| 42 | Instrument with Arize Phoenix | ✅ | `src/observability/tracing.py` | P3 |
| 42 | Govern its cost and latency | ✅ | `src/observability/golden_signals.py`, `pricing.py` (report only) | P5 |
| 42 | Harden with guardrails and an audit trail | ✅ | `src/guardrails/` | P4 |
| 42 | Document risk and compliance posture | ✅ | `docs/risk-register.md`, `docs/compliance.md` | P6 |
| 42 | Prove behaviour with agent-level evaluation and tests | ✅ | `reports/eval_report.json`; 236 offline tests | P5 |
| 42 | Deliver every artifact as committed evidence | ✅ | `reports/evidence_manifest.json` | P6 |

### A.5 Section 3.3 Expected solution, lines 46 to 52

| L | ref-doc says | Status | Proof and where | Phase |
|---|---|---|---|---|
| 48 | Typed state | ✅ | `src/state.py` `CopilotState` | P1 |
| 48 | Supervisor routing to intake, account-servicing, dispute, product-info workers | ✅ | `src/agents/` | P1 |
| 48 | Conditional routing | ✅ | `route_from_supervisor`, `route_after_input_guard`; `tests/test_routing.py` | P1 |
| 48 | Checkpointing | ✅ | `open_checkpointer` (`AsyncSqliteSaver`) in `src/graph.py` | P1 |
| 48 | Structured output | ✅ | `RouteDecision`, `FinalAnswer` in `src/schemas.py` | P1 |
| 49 | Custom MCP server, at least 2 tools and 1 resource, via langchain-mcp-adapters | ✅ | 7 tools, 1 resource; `src/mcp_client.py` | P1 |
| 49 | Engineered context: write, select, compress, isolate | ✅ | `src/context/write.py`, `select.py`, `compress.py`, `isolate.py` | P2 |
| 49 | ...summarization and quarantine of untrusted customer text | ✅ | `src/context/summarization.py`, `quarantine.py` | P2 |
| 49 | Tiered memory with verified cross-session persistence | ✅ | `logs/memory_test.log` PASS (real Gemini and LangMem) | P2 |
| 49 | Agentic-RAG tool over a banking-policy corpus | ✅ | `src/tools/rag_tool.py`; 12 documents | P2 |
| 50 | Phoenix instrumentation with a committed trace export | ✅ | `traces/phoenix_spans.parquet` | P3, P5 |
| 50 | Machine-generated tool-invocation log | ✅ | `logs/tool_calls.jsonl` | P3 |
| 50 | Evidence-linked failure-mode analysis | ✅ | `docs/failure-analysis.md` | P5 |
| 51 | Phoenix-derived golden-signals report | ✅ | `reports/golden_signals.json` | P5 |
| 51 | Cost/latency dashboard | ✅ | `reports/dashboard.png`, `reports/dashboard_data.csv` | P5 |
| 51 | Input/output guardrails, audit trail, secrets hygiene | ✅ | `src/guardrails/`, `logs/agent_actions.jsonl`, `.env.example`, `.gitignore` | P4 |
| 51 | Governance pack: risk register, model card, compliance mapping, output-risk classification | ✅ | Four documents in `docs/` | P6 |
| 52 | Agent-level evaluation: LLM-as-judge and hallucination | ✅ | `reports/eval_report.json`: hallucination rate 0.0; pre-fix; 30 scored cases (team decision) | P5 |
| 52 | Agent tests: routing-logic, loop/cascade guard, tool-contract | ✅ | `tests/test_routing.py`, `test_loops.py`, `test_tool_contracts.py` | P1, P2 |
| 52 | Reproducible local-run runbook | ✅ | `README.md` | P1 to P6 |

### A.6 Section 3.4 Applicable rules, lines 56 to 60

| L | Rule | Status | Proof and where |
|---|---|---|---|
| 56 | Evidence-in-Repo: only committed artifacts scored; a claim with no evidence scores zero; evidence with no producing code is discounted | ✅ | Manifest records producing commands. Screenshot and hand-written docs are labelled as such; `reports/eval_report.json` is a copy of the initial run |
| 57 | Citation-Resolves: cited run/span ids, log records and control files must resolve | ✅ | `scripts/verify_citations.py`; `reports/citation_check.json`: 6 docs, 26 controls, all resolve |
| 58 | Synthetic-Data: only synthetic data; numbers masked, never logged in plaintext | ✅ | `scripts/generate_synthetic_data.py`; `reports/pii_scan.json` 0 findings |
| 59 | Open-source and Gemini-only; pip and Python; no Docker or external DB | ✅ | Section 2 item 14: other providers only as unused transitive installs; the unused `guardrails-ai` pin was removed |
| 60 | Reproducibility: regenerable from one documented command with committed sample inputs | ✅ | Command documented; not exercised as one run (section 2, item 6) |

### A.7 Section 4 Technology stack, lines 66 to 78

| L | ref-doc says | Status | Proof and where |
|---|---|---|---|
| 66 | Fixed open-source toolchain, Gemini only, pip, no Docker or external DB service | ✅ | `requirements.txt`; SQLite and Chroma are local files |
| 70 | Python 3.11+ and LangGraph | ✅ | Python 3.12, langgraph 1.2.11 |
| 71 | Gemini the only provider | ✅ | `src/llm.py`, langchain-google-genai 4.4.0 |
| 72 | MCP Python SDK (stdio) and langchain-mcp-adapters | ✅ | mcp 1.30.0, adapters 0.3.2; `src/mcp_client.py` uses stdio |
| 73 | langgraph-checkpoint-sqlite and LangMem | ✅ | 3.1.1 and 0.0.30 |
| 74 | Chroma or FAISS and Sentence-Transformers, local | ✅ | Chroma 1.5.9, all-MiniLM-L6-v2 |
| 75 | Arize Phoenix and OpenTelemetry / openinference, local in-process | ✅ | arize-phoenix 14.6.0 (pinned; reason recorded in `requirements.txt`) |
| 76 | DeepEval (judge Gemini) and pytest | ✅ | deepeval 4.2.3 with `src/evaluation/gemini_judge.py` |
| 77 | Guardrails-AI or LLM Guard; Presidio; python-dotenv | ✅ | Presidio and python-dotenv used; guardrails are policy functions (allowed by L209); the unused `guardrails-ai` pin was removed |
| 78 | CLI required; FastAPI streaming optional | ✅ | `src/cli.py`; `src/api/` |

### A.8 Section 5.1 Acceptance criteria, lines 88 to 99

Full proof, weaknesses and phases are in section 5.3. Status per line:

| L | ID | Status | Location of proof | Phase |
|---|---|---|---|---|
| 88 | AC-01 account information grounded in tool data | ✅ | `logs/mcp_transcript.jsonl`, `reports/output_risk_sample.json`, `reports/eval_report.json` | P1 |
| 89 | AC-02 dispute capture, eligibility, draft for a human | ✅ | `src/agents/dispute.py`, `check_dispute_eligibility`, `reports/output_risk_sample.json` | P1, P2 |
| 90 | AC-03 cited policy answer, abstains when unsupported | ✅ | `src/tools/rag_tool.py`, `reports/eval_report.json` | P2 |
| 91 | AC-04 intent, clarify or escalate | ✅ | `tests/test_routing.py`, `logs/agent_actions.jsonl` | P1, P2 |
| 92 | AC-05 in-conversation and return-visit context | ✅ | `logs/memory_test.log`, `tests/test_memory_persistence.py` | P2 |
| 93 | AC-06 injection and other-customer refused; numbers never exposed | ✅ | `reports/redteam_results.json`, `tests/test_tool_gateway.py`, `reports/pii_scan.json` | P4 |
| 94 | AC-07 tool log; names reconcile | ✅ | `logs/tool_calls.jsonl`, `reports/tool_reconciliation.json` | P3 |
| 95 | AC-08 at least 3 real failures with ids, root cause, fix | ✅ | `docs/failure-analysis.md` (FA-01 to FA-03) | P5 |
| 96 | AC-09 golden signals and dashboard | ✅ | `reports/golden_signals.json`, `reports/dashboard.png`, `reports/dashboard_data.csv` | P5 |
| 97 | AC-10 guardrails in the I/O path and audit trail | ✅ | `src/graph.py`, `logs/agent_actions.jsonl` | P4 |
| 98 | AC-11 governance pack citing committed controls | ✅ | `docs/` (four documents plus catalog) | P6 |
| 99 | AC-12 DeepEval report and agent tests | ✅ | `reports/eval_report.json`, three test files | P5 |

### A.9 Section 5.2 Non-functional requirements, lines 105 to 111

Full proof is in section 5.4.

| L | ID | Status | Location of proof | Phase |
|---|---|---|---|---|
| 105 | NFR-01 no secrets; `.env.example`; `.gitignore` covers `.env` | ✅ | `.env.example`, `.gitignore`, `reports/secrets_scan.json` | P1, P4 |
| 106 | NFR-02 one command to run, a second to regenerate; sample inputs | ✅ | `README.md` "The two commands"; `data/sample_inputs/` | P1 to P6 |
| 107 | NFR-03 untrusted text quarantined | ✅ | `src/context/quarantine.py` | P2 |
| 108 | NFR-04 async; graceful degradation | ✅ | `src/llm.py`, `src/tools/resilience.py`, `tests/test_loops.py` | P1, P3 |
| 109 | NFR-05 synthetic data; numbers masked and never logged | ✅ | `src/common/masking.py`, `reports/pii_scan.json` | P1, P4 |
| 110 | NFR-06 evidence machine-generated with the code committed | ✅ | `reports/evidence_manifest.json` | P3 to P6 |
| 111 | NFR-07 at least 3 PR-driven `--no-ff` merges; no direct pushes to `main` | ⏳ | **Not done.** `docs/delivery-runbook.md` | Delivery |

### A.10 Section 6 Scope, lines 119 to 128

| L | ref-doc says | Status | Proof and where |
|---|---|---|---|
| 119 | In scope: the copilot and its full observability, cost governance, security, governance and evaluation surface | ✅ | Sections 5.1 to 5.6 |
| 120 | In scope: Phoenix tracing, golden signals and cost/latency governance, guardrails, audit, secrets hygiene, governance docs, agent evaluation and tests | ✅ | Sections 5.6, 5.7 |
| 121 | In scope: a CLI to drive requests and to regenerate traces and the evaluation | ✅ | `src/cli.py`: `chat`, `run`, `regenerate`, `eval`, `export` |
| 125 | Out of scope: Docker, Rancher, k8s, cloud deployment | ✅ | No such file tracked (`verify_submission.py`) |
| 126 | Out of scope: real core-banking connectivity or real data | ✅ | Synthetic data only |
| 127 | Out of scope: front-end polish; test volume for its own sake | ✅ | No polished UI; a simple optional Streamlit page exists (section 3) |
| 128 | Out of scope: advanced OAuth and live secrets rotation (document the approach) | ✅ | `docs/security-approach.md` |

### A.11 Section 7 Required artifacts, lines 134 to 194

| L | Row | Status | Location of proof | Phase |
|---|---|---|---|---|
| 134 | Checklist scored against; artifacts at or near the paths; Evidence-in-Repo and Citation-Resolves apply | ✅ | `verify_submission.py`: 49 of 49 | P6 |
| 140 | LangGraph graph: typed state, supervisor and at least 3 workers, conditional edges, checkpointer, structured output | ✅ | `src/graph.py` (4 workers) | P1 |
| 141 | MCP server, at least 2 tools and 1 resource, via adapters, committed transcript | ✅ | `mcp_server/`, `logs/mcp_transcript.jsonl` | P1 |
| 142 | Context engineering: write, select, compress, isolate, summarization, quarantine | ✅ | `src/context/` | P2 |
| 143 | Tiered memory: short and long term, cross-session test, committed log | ✅ | `src/memory/`, `tests/test_memory_persistence.py`, `logs/memory_test.log` | P2 |
| 144 | Agentic-RAG tool over a synthetic corpus | ✅ | `src/tools/rag_tool.py`, `data/policy_corpus/` | P2 |
| 150 | Phoenix tracer wired into the run path (called, not just imported) | ✅ | `init_tracing()` called in `src/cli.py` and `src/api/app.py` | P3 |
| 151 | Trace export: at least 1 full run; spans across multiple agents and every tool call; latencies | ✅ | `traces/phoenix_spans.parquet` | P3, P5 |
| 152 | Tool log: timestamp, agent/node, tool_name, args, result, latency_ms, status; names reconcile | ✅ | `logs/tool_calls.jsonl`, `reports/tool_reconciliation.json` | P3 |
| 153 | Failure analysis: at least 3 real failures, each with Phoenix run_id plus span_id (or tool-log record), root cause, fix | ✅ | `docs/failure-analysis.md` | P5 |
| 159 | Golden-signals report and producing script: latency by thinking/acting/tool, tokens, cost, accuracy, hallucination rate | ✅ | `reports/golden_signals.json`, `src/observability/golden_signals.py` | P5 |
| 160 | Dashboard screenshot and the data file it was drawn from | ✅ | `reports/dashboard.png`, `reports/dashboard_data.csv`. Note: Phoenix's cost column reads $0 (explained in the docs) | P5 |
| 166 | Guardrail code: input/output guardrails wired into the I/O path | ✅ | `src/guardrails/`, `src/graph.py` | P4 |
| 167 | Audit trail: actor, action, tool, decision, timestamp, plus middleware | ✅ | `logs/agent_actions.jsonl`, `src/guardrails/audit.py` | P4 |
| 168 | Secrets hygiene: `.env.example`, `.gitignore` | ✅ | Both files; scan clean | P1, P4 |
| 174 | Risk register: risk, category, likelihood, impact, mitigation citing a control, residual risk, owner | ✅ | `docs/risk-register.md` | P6 |
| 175 | Model card: model, data, intended use, limitations, failure modes citing the failure analysis, out-of-scope | ✅ | `docs/model-card.md` | P6 |
| 176 | Compliance mapping: EU AI Act, NIST AI RMF, DPDP obligation, how addressed, evidence | ✅ | `docs/compliance.md` | P6 |
| 177 | Output-risk: low/medium/high tiers, how high-risk is gated, a sample | ✅ | `docs/output-risk.md`, `reports/output_risk_sample.json` | P6 (code P4) |
| 183 | Evaluation report and harness: hallucination, faithfulness/relevance; Gemini judge | ✅ | `reports/eval_report.json`, `src/evaluation/harness.py`. Note: the run predates the three fixes; no re-run is required | P5 |
| 184 | Routing test: conditional edges route the right worker for given states | ✅ | `tests/test_routing.py` (route table, worker routing, ambiguous to intake, out-of-scope to escalation) | P1 |
| 185 | Loop test: a max-steps or recursion limit stops runaway loops | ✅ | `tests/test_loops.py` (step guard escalates; recursion limit set; no retry storm; bounded retries) | P1 |
| 186 | Tool-contract test: each tool's input/output schema and one error path | ✅ | `tests/test_tool_contracts.py` (14 tests; exact coverage in 5.6) | P1, P2 |
| 192 | README: single-command run, regeneration of traces and eval, sample inputs | ✅ | `README.md` | P1 to P6 |
| 193 | Git history: at least 3 PR-driven merges; no direct pushes to `main` | ⏳ | **Pending delivery** (NFR-07) | Delivery |
| 194 | Bonus (optional): async FastAPI streaming | ✅ | `src/api/`, `logs/api_demo.log` | P6 |

### A.12 Section 8 Producing the evidence, lines 200 to 219

| L | ref-doc says | Status | Location of proof | Phase |
|---|---|---|---|---|
| 200 | Enable Phoenix locally (`arize-phoenix`, `openinference-instrumentation-langchain`; UI at localhost:6006) as the single source for trace, latency, token and cost evidence | ✅ | Both packages in `requirements.txt`; `reports/dashboard.png` is the local UI | P3 |
| 204 | Trace export: Parquet or JSONL of OTel spans, from a full conversation | ✅ | `traces/phoenix_spans.parquet` via `python -m src.cli export --parquet` (the brief's `px.Client()` does not exist in the pinned version; documented) | P3, P5 |
| 205 | Tool log: a logging wrapper on every tool | ✅ | `src/observability/tool_logging.py` via `src/tools/registry.py` | P3 |
| 206 | Failure analysis: at least 3 real failures from Phoenix traces | ✅ | `docs/failure-analysis.md` | P5 |
| 207 | Golden signals: a script reads Phoenix spans: p50/p95 by span type, token totals, cost from tokens and published price, accuracy and hallucination from the eval | ✅ | `src/observability/golden_signals.py` | P5 |
| 208 | Dashboard: Phoenix screenshot and the CSV export | ✅ | `reports/dashboard.png`, `reports/dashboard_data.csv`. Note: Phoenix's cost column reads $0 (explained in the docs) | P5 |
| 209 | Guardrail code: validators or policy functions wired into the I/O nodes | ✅ | `src/guardrails/`, `src/graph.py` | P4 |
| 210 | Audit trail: middleware appending actor, action, tool, decision, timestamp | ✅ | `src/guardrails/audit.py` | P4 |
| 211 | Governance pack: four documents, each entry citing a control | ✅ | `docs/` | P6 |
| 212 | Evaluation report: DeepEval over a golden set writing `reports/eval_report.json` with the harness | ✅ | `reports/eval_report.json`. Note: the run predates the three fixes; no re-run is required | P5 |
| 213 | Agent tests: three pytest files | ✅ | `tests/` | P1, P2 |
| 217 | Good to have: FastAPI streaming endpoint | ✅ | `src/api/` | P6 |
| 217 | Good to have: a demonstrated local run (screenshot or log) | ✅ | `logs/api_demo.log` | P6 |
| 218 | Good to have: PII-redaction middleware (Presidio) with a before/after sample | ✅ | `src/guardrails/pii.py`, `reports/pii_redaction_sample.json` | P4 |
| 218 | Good to have: a small red-team attack set and results | ✅ | `data/redteam/attacks.jsonl`, `reports/redteam_results.json` | P4 |
| 219 | Good to have: an optimization note with measured before/after latency or cost (two Phoenix-derived reports) | ❌ | **Not done** | |
| 223 | Closing statement | ➖ | No requirement | |

### A.13 Result of the line-by-line pass

- **Every requirement-bearing line of `ref-doc.md` was traced.** Lines with no
  requirement (headings, prose, the closing note) are marked ➖ or omitted.
- **Not met:** L111 and L193 (PR merges, delivery step) and L219 (optimization
  note, good-to-have).
- **Met with a stated weakness:** L52 and L99 and L183 and L212 (pre-fix eval),
  L38 (no cost enforcement, no continuous evaluation), L60 and L106
  (regenerate not exercised as one run), L160 and L208 (Phoenix screenshot still
  shows cost $0, now explained in the docs).
