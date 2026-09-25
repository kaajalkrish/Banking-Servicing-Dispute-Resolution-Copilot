# Control Catalog

> Stable control IDs (`CTL-xx`) that the governance pack (risk register, model
> card, compliance mapping, output-risk doc) cites instead of re-describing
> each control inline. Every entry below names a real, committed code path
> and symbol — verified against the actual source at the time of writing,
> not assumed — plus the evidence artifact that shows it operating.
> `scripts/verify_citations.py` (extended in P6-03) checks that every
> `CTL-xx` cited elsewhere in `docs/*.md` exists here and that its code
> path/symbol and evidence path still exist on disk.

| ID | Control | Code path (symbol) | Evidence artifact |
|---|---|---|---|
| CTL-01 | Input guard: PII masking at ingress | `src/guardrails/ingress.py` (`sanitize_ingress`) | `logs/agent_actions.jsonl` (`action=sanitize_input`, `reason_code=pii_detected`) |
| CTL-02 | Input guard: injection detection | `src/guardrails/injection.py` (`detect_injection`) | `reports/redteam_results.json` |
| CTL-03 | Input guard: cross-customer reference detection | `src/guardrails/input.py` (`detect_cross_customer_reference`) | `logs/agent_actions.jsonl` (`reason_code=cross_customer_reference`) |
| CTL-04 | Input guard: block decision + safe refusal | `src/guardrails/input.py` (`evaluate_input`); `src/graph.py` (`ingress_input_guard_node`, `route_after_input_guard`) | `logs/agent_actions.jsonl` (`action=block_input`, `decision=blocked`) |
| CTL-05 | Tool-scope gateway: authenticated-customer enforcement | `src/tools/gateway.py` (`scope_denial`); wired via `src/agents/_common.py` (`get_tool`) | `logs/agent_actions.jsonl` (denial records, `actor=tool_gateway`) |
| CTL-06 | Context quarantine of untrusted customer text | `src/context/quarantine.py` | `docs/architecture.md` §7 (quarantine strategy description); `docs/architecture.md` §2 (trust boundaries) |
| CTL-07 | PAN / account-number masking (all logs and outputs) | `src/common/masking.py` (`mask_pan`, `mask_account`, `mask_obj`, `luhn_check`) | `reports/pii_scan.json` (0 unmasked findings outside the allow-listed sample) |
| CTL-08 | Output guard: leakage / other-customer-id masking, refund & dispute-outcome rewrite, system-prompt-leak redaction | `src/guardrails/output.py` (`sanitize_output`) | `logs/agent_actions.jsonl` (`action=sanitize_output`) |
| CTL-09 | Output-risk classification + human-in-the-loop gate | `src/guardrails/output_risk.py` (`classify_and_gate`); `src/graph.py` (`finalize_node`) | `reports/output_risk_sample.json` (P6-07) |
| CTL-10 | Audit trail of consequential actions | `src/guardrails/audit.py` (`record_action`); customer id is hashed, never logged raw (`hash_customer_ref`) | `logs/agent_actions.jsonl` |
| CTL-11 | Tool-invocation log (every tool call) | `src/observability/tool_logging.py`; `src/tools/registry.py` (`build_tools`) so no tool call can bypass it | `logs/tool_calls.jsonl`; `reports/tool_reconciliation.json` |
| CTL-12 | Resilient tool wrapper (timeout/retry, graceful degradation) | `src/tools/resilience.py` (`resilient_ainvoke`, `tool_failure`) | `tests/test_loops.py` (no retry storm on a failing tool; timeout path) |
| CTL-13 | LLM call retry/backoff (transient 429/5xx/timeout) | `src/llm.py` (`ainvoke_with_backoff`, `_is_transient`) | commit history (`fix(llm): treat bare TimeoutError as transient and retry it`) |
| CTL-14 | Soft step-count guard (loop/cascade prevention) | `src/agents/supervisor.py` (`step_count`/`max_steps` check) | `tests/test_loops.py` |
| CTL-15 | Hard recursion-limit guard + graceful degrade | `src/config.py` (`recursion_limit`); `src/cli.py` (`_invoke_turn`, catches `GraphRecursionError`) | `tests/test_cli_recursion_guard.py`; commit history (`fix(graph): widen recursion-limit safety margin and degrade gracefully`) |
| CTL-16 | Presidio PII detection (banking-specific recognizers) | `src/guardrails/pii.py` (`detect_pii`, `anonymize_text`) | `reports/pii_redaction_sample.json` |
| CTL-17 | Secrets scanner (working tree + git history) | `scripts/check_secrets.py` | `reports/secrets_scan.json` |
| CTL-18 | Evidence PII scanner (logs/traces/reports) | `scripts/scan_evidence_for_pii.py` | `reports/pii_scan.json` |
| CTL-19 | Red-team attack set + harness | `data/redteam/attacks.jsonl`; `scripts/run_redteam.py` | `reports/redteam_results.json`, `docs/redteam-results.md` |
| CTL-20 | Phoenix tracing (called on the run path) | `src/observability/tracing.py` (`init_tracing`, `traced_run`) | `traces/phoenix_spans.parquet` |
| CTL-21 | run_id stamping for citation resolution | `src/common/ids.py` (`new_run_id`) | resolved by `scripts/verify_citations.py` |
| CTL-22 | Agentic-RAG grounding + abstention | `src/tools/rag_tool.py` (`PolicySearchTool`, `answer_node`, `abstain_node`) | `reports/eval_report.json` (faithfulness/hallucination scores) |
| CTL-23 | Golden-set evaluation (accuracy, hallucination, faithfulness, relevancy) | `src/evaluation/harness.py` (`run_eval`); `src/evaluation/gemini_judge.py` (`GeminiJudge`) | `reports/eval_report.json` |
| CTL-24 | Golden-signals / cost-latency computation | `src/observability/golden_signals.py` (`compute_golden_signals`) | `reports/golden_signals.json` |
| CTL-25 | Draft-only dispute outcomes (never auto-commits money movement) | `src/agents/dispute.py` (always sets `requires_human_review=True`) | `docs/failure-analysis.md` (design rationale, D-13) |
| CTL-26 | AI disclosure to the customer (CLI, streaming API and Streamlit UI) | `src/common/disclosure.py` (`AI_DISCLOSURE`); `src/cli.py` (`chat_banner`); `src/api/streaming.py` (`stream_turn`); `src/ui/app.py` (`main`) | `tests/test_cli_disclosure.py`; `tests/test_ui_app.py`; `logs/api_demo.log` |
