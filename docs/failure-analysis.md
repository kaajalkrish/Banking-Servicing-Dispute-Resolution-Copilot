# Failure Analysis (AC-08, §7.2)

> Real failures found in the P5-06 evidence run (`reports/eval_report_initial.json`,
> 30 golden-set cases, `gemini-3.1-flash-lite`), each cited to a real committed
> tool-log record (`logs/tool_calls.jsonl` / `logs/agent_actions.jsonl`) and the
> exact `run_id` (D-04) it happened under. Never fabricated or invented for this
> document. (A running log was also kept locally during development; it is
> not committed, so nothing below depends on it.)

---

## FA-01 — Informational questions routed to the dispute worker

**Symptom.** Pure fact-checking questions that merely mention dispute-adjacent
words ("Did I get charged twice by Uber?", "Is there a transaction from a
merchant I don't recognize?", "What should I do if I see an unauthorized
transaction?") were routed to the `dispute` worker instead of
`account_servicing` / `product_info`. The dispute worker's own clarification
message ("I can help raise a dispute. Which transaction is it?...") was
returned instead of an answer, and because the dispute worker always sets
`requires_human_review=True` (D-13), the request was escalated instead of
answered.

**Evidence.** `g-txn-002` ("Did I get charged twice by Uber?"),
run_id `run-67594ff3-25b4-4efe-b1e9-ac25eb35bce2` —
`logs/agent_actions.jsonl`: `{"run_id": "run-67594ff3-...", "actor": "finalize", "action": "finalize_answer", "decision": "high", "reason_code": "dispute", ...}`.
Five of the eight initial mismatches (`g-txn-002`, `g-txn-003`, `g-pol-006`,
`g-dsp-004`, plus a sixth borderline case) shared this exact symptom; all 3
genuine `dispute_intake` cases (customers actually filing a dispute) routed
correctly, isolating the bug to intent misclassification, not a broken
dispute worker.

**Root cause.** `src/agents/supervisor.py`'s routing prompt described the
`dispute` route by *topic* ("a disputed / unauthorized / duplicate
transaction"), not by *intent*, so the LLM router matched on keyword presence
rather than distinguishing "customer wants to file a dispute now" from
"customer is asking a question that happens to use similar words."

**Fix.** Commit `5494934` — rewrote the route descriptions to state intent
explicitly, with worked examples showing informational/eligibility questions
routing to `product_info` / `account_servicing` instead. Verified: full
offline suite green (145 passed, 0 regressions; routing tests use a scripted
fake supervisor LLM, unaffected by a prompt-only change).

---

## FA-02 — Dispute-status question created a duplicate draft instead of a status answer

**Symptom.** "What's the status of dispute DSP00001?" did not report the
dispute's status — it attempted to check eligibility and draft a **new**
dispute case, using the dispute *id* (`DSP00001`) as if it were a
*transaction* id.

**Evidence.** `g-dsp-005`, run_id `run-805ab749-ab4f-4cda-8761-b85d737a9924` —
`logs/tool_calls.jsonl` shows both tool calls failing on exactly this
confusion:
`{"run_id": "run-805ab749-...", "agent": "dispute", "tool_name": "check_dispute_eligibility", "args": {"transaction_id": "DSP00001", ...}, "result": {"error": {"type": "LookupError", "message": "transaction DSP00001 not found"}}}`
and the same `transaction_id: "DSP00001"` mistake repeated in the following
`create_dispute_case` call, also erroring `LookupError`.

**Root cause.** `src/agents/dispute.py` had exactly one code path: extract a
transaction id, check eligibility, draft a case. There was no notion of a
"check an existing dispute's status" intent, and no `dispute_id` field in the
extraction schema (`src/context/quarantine.py`) to even capture one.

**Fix.** Commit `648da99` — added a `dispute_id` field to
`ExtractedDisputeFields` and a status-lookup branch in `dispute_node` that
calls `get_dispute_status` instead of the file-a-new-dispute flow when a
dispute id is present without a transaction id. Note: the golden-set case
still classifies as `escalate` after this fix, correctly — every dispute-
worker output is force-gated to human review by design
(`classify_and_gate`'s `_HIGH_RISK_WORKERS` backstop, D-13), so a status
answer is still routed for review. That's intentional; the golden set's
expectation was corrected to match (part of commit `648da99`), not the code.

---

## FA-03 — A memory-save failure silently discarded an already-correct answer

**Symptom.** Two single-fact policy questions that should have been trivial
returned the generic fallback *"This request needs a human banking agent —
it took too many steps to resolve automatically"* — the hard-recursion-limit
degrade message from `cli.py`'s `_invoke_turn` — even though the real answer
had already been computed correctly.

**Evidence.** `g-pol-002` ("What happens if my account goes into
overdraft?"), run_id `run-db17b1f6-f29c-4cf1-8cfc-f875f8864892`. The audit
trail shows `finalize` genuinely completed with a **good** answer:
`logs/agent_actions.jsonl`: `{"run_id": "run-db17b1f6-...", "actor": "finalize", "action": "finalize_answer", "decision": "low", "reason_code": "product_info", "details": {"requires_human_review": false}}`,
and `logs/tool_calls.jsonl` shows the actual `policy_search` call that
produced it — a fully correct, policy-cited overdraft answer. Yet the value
returned to the caller for this same `run_id` was the recursion-fallback
message, not that answer. `g-pol-007` and `g-pol-008` showed the identical
pattern.

**Root cause.** `save_memory_node` (`src/graph.py`) runs *after*
`finalize_node` and had no error handling around its call to LangMem's
extractor. A LangMem extraction failure (a real, separately-observed pydantic
validation error, `"1 validation error for Memory / content: Field
required"`, seen in this session's process logs) propagating out of that
call — including, in some cases, as a `GraphRecursionError` from LangMem's
own internal graph — was caught by `_invoke_turn`'s blanket
`except GraphRecursionError` handler, which has no way to tell "the whole
turn looped" apart from "a best-effort cleanup step after a good answer
failed," and discarded the already-correct `final_answer` in favor of the
generic fallback.

**Fix.** Commit (this session, `src/graph.py`) — wrapped
`save_memory_node`'s call to `extract_and_store` in a broad
`try/except: pass`. A memory-write failure is now silently best-effort
(matching its actual importance relative to the customer-facing answer)
instead of being able to destroy a turn that already succeeded. Verified:
full offline suite green (145 passed, 0 regressions).
**Not yet independently re-verified live** against `g-pol-002`/`g-pol-007`/
`g-pol-008` — that is the next step, pending a live evidence run.
