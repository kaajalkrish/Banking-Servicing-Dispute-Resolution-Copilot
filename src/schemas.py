"""Structured-output schemas for node boundaries (ref-doc.md §3.3 b1, §7.1).

Nodes emit these pydantic models (via the LLM's structured-output mode or
constructed directly) so routing and answers are validated, typed data rather
than free text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskTier = Literal["low", "medium", "high"]

RouteTarget = Literal[
    "intake",
    "account_servicing",
    "dispute",
    "product_info",
    "escalate_human",
    "finalize",
]


class RouteDecision(BaseModel):
    """Supervisor's structured routing decision."""

    worker: RouteTarget = Field(description="Which worker/node should handle the request next.")
    reason: str = Field(description="Short justification for the route.")
    needs_clarification: bool = Field(
        default=False, description="True if the request is ambiguous and intake should clarify."
    )


class Citation(BaseModel):
    """A grounded reference into the policy corpus."""

    doc_id: str
    section: str | None = None


class WorkerResult(BaseModel):
    """Result produced by a worker agent."""

    worker: str
    content: str
    citations: list[Citation] = Field(default_factory=list)
    requires_human_review: bool = False


class FinalAnswer(BaseModel):
    """The finalized answer returned to the customer."""

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    requires_human_review: bool = False
    risk_tier: RiskTier = "low"
    escalated: bool = False
