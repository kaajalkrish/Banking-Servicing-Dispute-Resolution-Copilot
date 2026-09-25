"""Customer-facing AI disclosure, shown by every interface (CLI, API).

Transparency to the customer that they are talking to an AI system, and what
it cannot do (docs/compliance.md, EU AI Act transparency obligation). One
constant so the CLI and the streaming API cannot drift apart.
"""

from __future__ import annotations

AI_DISCLOSURE = (
    "You are chatting with an automated AI assistant, not a person. It can "
    "make mistakes, and it cannot approve refunds or disputes: a human "
    "banking agent makes those decisions."
)
