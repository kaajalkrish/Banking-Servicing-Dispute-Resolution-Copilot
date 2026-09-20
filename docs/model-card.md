# Model and System Card

Banking Servicing & Dispute-Resolution Copilot (BC-AAIE-HACK-01). This card
describes the whole system (models, data, controls), not only the language
model. Control IDs (`CTL-xx`) refer to `docs/control-catalog.md`; risks
(`R-xx`) to `docs/risk-register.md`; failures (`FA-xx`) to
`docs/failure-analysis.md`.

## 1. System summary

A LangGraph multi-agent copilot for retail-bank servicing. A supervisor routes
each customer request to one of four workers (intake, account servicing,
dispute, product info) or to a human escalation node. Workers call tools
served by a custom MCP server and an agentic-RAG policy search. Input and
output guardrails wrap every turn, and every turn is traced (Arize Phoenix),
logged and audited. The full design is in `docs/architecture.md`.

## 2. Models

| Role | Model | Where set |
|---|---|---|
| Workers (answers, extraction) | `gemini-3.5-flash` by default | `GEMINI_MODEL` in `src/config.py`, `.env.example` |
| Supervisor (routing) | `gemini-3.5-flash-lite` by default | `GEMINI_MODEL_FAST` |
| Evaluation judge (DeepEval) | `gemini-3.5-flash` by default | `GEMINI_JUDGE_MODEL` |
| Long-term memory extraction | the worker model, through LangMem | `src/memory/long_term.py` |
| Embeddings (RAG, memory search) | `all-MiniLM-L6-v2` via Sentence-Transformers, run locally | `src/common/embeddings.py` |

Google Gemini is the only model provider (a rule of the brief). The
configured defaults were not always the models that ran: free-tier daily
quotas were exhausted repeatedly, so runs were moved between Gemini models.
The evaluation report (`reports/eval_report.json`) was produced with
`gemini-3.1-flash-lite` for both the workers and the judge, and the golden
signals in `reports/golden_signals.json` cover spans from three Gemini models
(`gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`). No
model was fine-tuned.

## 3. Data

All data is synthetic (Synthetic-Data Rule); no real customer or account data
exists anywhere in the repository.

| Data | What it is | Produced by |
|---|---|---|
| Banking records | 5 customers, 9 accounts, 134 transactions, 3 seed disputes; PANs are Luhn-valid numbers on a reserved test BIN | `scripts/generate_synthetic_data.py --seed 42` (deterministic), output in `data/synthetic/` |
| Policy corpus | 12 synthetic policy documents (fees, overdraft, cards, disputes, KYC, ...); mortgages, cryptocurrency and investments are deliberately absent so abstention can be tested | `data/policy_corpus/` |
| Golden set | 47 authored cases, of which the first 30 are scored (a free-tier quota limit, see `plan.md`) | `data/golden_set/golden.jsonl` |
| Red-team set | 37 attacks across 8 categories, tagged with OWASP LLM ids | `data/redteam/attacks.jsonl` |

Account numbers and PANs are masked wherever they are shown or logged
(CTL-07); the evidence scanner checks this over every committed log, trace
and report (CTL-18).

## 4. Intended use

- Answer a customer's account questions (balance, recent transactions,
  statement summary) grounded in tool output (AC-01).
- Take the first steps of a dispute: capture the details, check eligibility
  against the dispute-window policy, and draft a case for a human agent
  (AC-02).
- Answer product, fee and servicing-policy questions with a citation, and
  abstain when the corpus does not support an answer (AC-03).
- Ask a clarifying question or escalate to a human when a request is
  ambiguous or out of scope (AC-04).
- Remember context within a conversation and across visits (AC-05).

The intended user is a bank customer using a chat interface; the intended
operator is a bank team that reviews escalated and dispute items.

## 5. Out-of-scope uses

Not supported, and not to be assumed safe:

- **Any real customer, account or payment data.** The system has only been
  built and evaluated on synthetic data (risk R-13).
- **Moving money, approving refunds or deciding disputes.** No tool can do
  this and the copilot is designed never to promise it (CTL-25, CTL-08).
- **Production authentication.** The customer id is taken as already
  authenticated; OAuth and secrets rotation are described, not built
  (`docs/security-approach.md`).
- **Legal, credit, lending, investment or tax advice**, and any decision
  with legal effect on a person.
- **Languages other than English**, and accessibility channels (voice).
- Containerized or cloud deployment (out of scope for this cut).

## 6. Human oversight

| Mechanism | Behaviour | Control |
|---|---|---|
| Dispute gate | Every answer from the dispute worker is forced to human review, whatever the worker set; no outcome is ever committed | CTL-09, CTL-25 |
| Output-risk tiers | Answers are tiered low (cited policy), medium (account data), high (dispute or escalation); high is gated to a human | CTL-09 |
| Escalation | Out-of-scope, unsafe or looping requests hand off to a human with a safe message | CTL-04, CTL-14, CTL-15 |
| Abstention | When retrieval does not support an answer, the copilot says so instead of guessing | CTL-22 |
| AI disclosure | The chat CLI, the streaming API's first event and the top of the Streamlit UI page tell the customer they are talking to an AI and that a human decides refunds and disputes | CTL-26 (`src/common/disclosure.py`) |
| Audit | Consequential actions and every tool call are logged | CTL-10, CTL-11 |

## 7. Evaluation

Source: `reports/eval_report.json`, produced by the DeepEval harness
(`src/evaluation/harness.py`, CTL-23) with a Gemini judge. 30 golden-set cases.

**This is the run made before the three fixes for FA-01, FA-02 and FA-03. It
has not been re-scored, so it does not show their effect.**

| Metric | Value |
|---|---|
| Accuracy (observed behaviour matches the expected answer / abstain / refuse / escalate) | 0.60 (18 of 30) |
| Hallucination rate | 0.0 (over the 27 cases scored for it) |
| Faithfulness, mean | 0.98 |
| Answer relevancy, mean | 0.74 |

Accuracy by category (fraction matching):

| Category | Result |
|---|---|
| account_balance | 1.00 |
| account_statement | 1.00 |
| dispute_intake | 1.00 |
| abstention | 0.67 |
| policy_question | 0.50 |
| ambiguous | 0.50 |
| account_transactions | 0.33 |
| dispute_eligibility | 0.00 |
| dispute_status | 0.00 |

Categories hold only 1 to 12 cases each, so the per-category figures are
indicative, not statistically meaningful. The judge is itself an LLM.

Other measured results: the red-team run passed 37 of 37 attacks, 4 of them
documented known gaps that are counted as accepted (`reports/redteam_results.json`,
`docs/redteam-results.md`). Latency and cost are in `reports/golden_signals.json`
and cover all runs recorded in Phoenix, including failed ones: latency p50 /
p95 is about 0.7 s / 7.5 s for model calls (thinking), 3.6 s / 20.2 s for tool
calls, over 6,820 spans with a 12.0% span error rate (the causes include
free-tier quota errors and the failures in `docs/failure-analysis.md`; the
split was not measured). Token volume was 566,547 input and 97,826 output, which is about $0.44
at the paid Standard list price (the runs used the free tier, so nothing was
billed). Phoenix's own dashboard (`reports/dashboard.png`) shows cost $0
because no model prices are configured in Phoenix; the estimate above is computed
separately from Google's published prices.

## 8. Known limitations and failure modes

**Documented and fixed (root cause and fix commit in `docs/failure-analysis.md`).**

- **FA-01.** Informational questions that mention dispute-like words were
  routed to the dispute worker and escalated instead of answered.
- **FA-02.** "What is the status of dispute DSP00001?" tried to draft a
  duplicate dispute instead of reporting status.
- **FA-03.** A failure while saving long-term memory discarded an answer that
  had already been computed correctly.

**Seen in the same evaluation run but not analysed or fixed.** The cases
below are in `reports/eval_report.json`; their causes have not been
investigated:

- **Over-abstention.** `g-pol-010` (identity-verification documents) and
  `g-pol-011` (managing the account in the mobile app) abstained although a
  relevant policy document exists (`POL-KYC`, `POL-DIGITAL-BANKING`).
- **Answered where the label says abstain.** `g-abs-002` (cryptocurrency)
  answered "no, not offered" and cited the corpus section "Account Types Not
  Offered", which does exist, so this may be a labelling question as much as a
  fault; it has not been resolved.
- **Generic fallback on an ambiguous request.** `g-amb-001` ("I need help with
  something.") returned the "took too many steps" fallback. The symptom matches
  FA-03, but a shared root cause has not been confirmed.

**Structural limitations.**

- Injection detection is literal-pattern based; encoded or obfuscated payloads
  (base64, leetspeak, zero-width characters) are not detected (risk R-01).
- Long-term memory stores customer statements without verification or expiry
  (risk R-10).
- The evaluation set is small (30 scored cases) and synthetic, with an LLM
  judge; no evaluation on real customer language has been done (risk R-13).
- No per-customer rate limit or spend cap; provider quotas were hit repeatedly
  (risks R-09, R-12).
- No fairness or bias evaluation was performed. Behaviour for different
  customer groups, names or dialects is unmeasured.
- Audit logs are local, plain JSONL (risk R-17).
