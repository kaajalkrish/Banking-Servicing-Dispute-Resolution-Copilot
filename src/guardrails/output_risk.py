"""Output-risk classification with a human-in-the-loop gate (§7.5, AC-02, AC-04).

Tiers per ref-doc.md's own definition, by content sensitivity:

- **low**: general cited policy info (product_info's normal answers, intake's
  clarifying questions) — no financial commitment, no account-specific data.
- **medium**: account-specific masked data (account_servicing's balance/
  transaction/statement/service-request answers).
- **high**: dispute outcomes and any human escalation — a dispute worker's
  answer is always gated to human review (D-13: the copilot never commits an
  outcome), and this is a backstop: even if a future bug in dispute_node
  forgot to set requires_human_review, this classifier forces it back on for
  anything routed through the dispute/escalate_human workers.

Tier is deliberately independent of the `requires_human_review` flag a worker
already set for an unrelated reason — e.g. product_info's abstention sets
requires_human_review=True (a human may want to help further) but the content
itself (an honest "I don't know") is not high-risk, so it stays "low".
"""

from __future__ import annotations

from typing import Any, Literal

RiskTier = Literal["low", "medium", "high"]

_HIGH_RISK_WORKERS = {"dispute", "escalate_human"}
_MEDIUM_RISK_WORKERS = {"account_servicing"}
# product_info, intake default to low.


def classify_and_gate(worker: str, content: str, *, requires_human_review: bool) -> dict[str, Any]:
    if worker in _HIGH_RISK_WORKERS:
        tier: RiskTier = "high"
        requires_human_review = True  # backstop: always gated, regardless of what the worker set
    elif worker in _MEDIUM_RISK_WORKERS:
        tier = "medium"
    else:
        tier = "low"

    return {"risk_tier": tier, "requires_human_review": requires_human_review, "content": content}
