"""Data access for the MCP server: reads synthetic JSON, returns MASKED values.

Full account/card numbers stay server-side only; every value returned to a
caller is masked (NFR-05, AC-06). Accounts are referenced by their last-4
``account_ref`` so no full number needs to cross the boundary. Disputes and
service requests created at runtime are held in a process-local registry seeded
from the synthetic dispute file (the stdio server is one process per session).
"""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Any

from src.common.masking import mask_account, mask_pan

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"
_lock = threading.Lock()


def _load(name: str) -> list[dict]:
    return json.loads((_DATA_DIR / name).read_text(encoding="utf-8"))


class Bank:
    """In-memory synthetic bank backed by the committed JSON datasets."""

    def __init__(self) -> None:
        self.customers = {c["customer_id"]: c for c in _load("customers.json")}
        self.accounts = _load("accounts.json")
        self.transactions = _load("transactions.json")
        self._disputes = {d["dispute_id"]: dict(d) for d in _load("disputes_seed.json")}
        self._service_requests: dict[str, dict] = {}
        self._seq = 1000

    # --- resolution helpers (full numbers never leave this class) ---
    def _accounts_for(self, customer_id: str) -> list[dict]:
        return [a for a in self.accounts if a["customer_id"] == customer_id]

    def _resolve(self, customer_id: str, account_ref: str | None) -> dict:
        owned = self._accounts_for(customer_id)
        if not owned:
            raise LookupError(f"no accounts for customer {customer_id}")
        if account_ref is None:
            if len(owned) == 1:
                return owned[0]
            refs = ", ".join(a["account_number"][-4:] for a in owned)
            raise ValueError(f"multiple accounts; specify account_ref (last 4): {refs}")
        ref = account_ref[-4:]
        for a in owned:
            if a["account_number"].endswith(ref):
                return a
        raise LookupError(f"account ****{ref} not found for customer {customer_id}")

    def _next_id(self, prefix: str) -> str:
        with _lock:
            self._seq += 1
            return f"{prefix}{self._seq:05d}"

    # --- tool-backing operations (all return masked values) ---
    def account_balance(self, customer_id: str, account_ref: str | None = None) -> dict[str, Any]:
        a = self._resolve(customer_id, account_ref)
        return {
            "account_ref": a["account_number"][-4:],
            "account_display": mask_account(a["account_number"]),
            "type": a["type"],
            "balance": a["balance"],
            "currency": a["currency"],
            "status": a["status"],
        }

    def recent_transactions(
        self, customer_id: str, account_ref: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        a = self._resolve(customer_id, account_ref)
        txns = [t for t in self.transactions if t["account_number"] == a["account_number"]]
        txns = sorted(txns, key=lambda t: t["date"], reverse=True)[: max(1, min(limit, 50))]
        items = [
            {
                "transaction_id": t["transaction_id"],
                "date": t["date"],
                "amount": t["amount"],
                "currency": t["currency"],
                "merchant": t["merchant"],
                "category": t["category"],
                "status": t["status"],
                "unrecognized": t.get("unrecognized", False),
                "duplicate_of": t.get("duplicate_of"),
            }
            for t in txns
        ]
        return {"account_ref": a["account_number"][-4:], "count": len(items), "transactions": items}

    def statement_summary(self, customer_id: str, account_ref: str | None = None) -> dict[str, Any]:
        a = self._resolve(customer_id, account_ref)
        txns = [t for t in self.transactions if t["account_number"] == a["account_number"]]
        by_cat: dict[str, float] = {}
        for t in txns:
            by_cat[t["category"]] = round(by_cat.get(t["category"], 0.0) + t["amount"], 2)
        return {
            "account_ref": a["account_number"][-4:],
            "transaction_count": len(txns),
            "total_spend": round(sum(t["amount"] for t in txns), 2),
            "by_category": by_cat,
            "currency": a["currency"],
        }

    def create_dispute(
        self, customer_id: str, transaction_id: str, reason: str, description: str = ""
    ) -> dict[str, Any]:
        # Find the transaction and confirm it belongs to the customer.
        txn = next((t for t in self.transactions if t["transaction_id"] == transaction_id), None)
        if txn is None:
            raise LookupError(f"transaction {transaction_id} not found")
        owned_accts = {a["account_number"] for a in self._accounts_for(customer_id)}
        if txn["account_number"] not in owned_accts:
            raise PermissionError("transaction does not belong to this customer")
        did = self._next_id("DSP")
        rec = {
            "dispute_id": did,
            "transaction_id": transaction_id,
            "account_ref": txn["account_number"][-4:],
            "reason": reason,
            "status": "draft",  # never auto-resolved; human agent decides (D-13)
            "opened_date": date.today().isoformat(),
            "description": description[:500],
        }
        self._disputes[did] = rec
        return {k: v for k, v in rec.items() if k != "account_number"}

    def dispute_status(self, dispute_id: str) -> dict[str, Any]:
        rec = self._disputes.get(dispute_id)
        if rec is None:
            raise LookupError(f"dispute {dispute_id} not found")
        return {
            "dispute_id": rec["dispute_id"],
            "transaction_id": rec["transaction_id"],
            "reason": rec["reason"],
            "status": rec["status"],
            "opened_date": rec["opened_date"],
        }

    def submit_service_request(
        self, customer_id: str, request_type: str, details: str = ""
    ) -> dict[str, Any]:
        if customer_id not in self.customers:
            raise LookupError(f"customer {customer_id} not found")
        allowed = {"card_replacement", "statement_copy", "limit_change"}
        if request_type not in allowed:
            raise ValueError(f"request_type must be one of {sorted(allowed)}")
        sid = self._next_id("SR")
        rec = {
            "request_id": sid,
            "customer_id": customer_id,
            "request_type": request_type,
            "status": "received",
            "details": details[:500],
        }
        self._service_requests[sid] = rec
        return {"request_id": sid, "request_type": request_type, "status": "received"}

    def check_dispute_eligibility(
        self, customer_id: str, transaction_id: str, reason: str
    ) -> dict[str, Any]:
        """Deterministic eligibility check against the dispute-windows reference.

        Rules: the window (days from posting date) for the given reason; the
        transaction must belong to the customer; a transaction already under an
        open/under-review dispute cannot be disputed again (§ dispute_timelines
        'One Dispute Per Transaction').
        """
        window_key = _REASON_TO_WINDOW_KEY.get(reason)
        if window_key is None:
            raise ValueError(f"reason must be one of {sorted(_REASON_TO_WINDOW_KEY)}")

        txn = next((t for t in self.transactions if t["transaction_id"] == transaction_id), None)
        if txn is None:
            raise LookupError(f"transaction {transaction_id} not found")
        owned_accts = {a["account_number"] for a in self._accounts_for(customer_id)}
        if txn["account_number"] not in owned_accts:
            raise PermissionError("transaction does not belong to this customer")

        window_days = DISPUTE_WINDOWS[window_key]
        txn_date = date.fromisoformat(txn["date"])
        days_since = (date.today() - txn_date).days

        existing = [
            d
            for d in self._disputes.values()
            if d["transaction_id"] == transaction_id and d["status"] in ("draft", "open", "under_review")
        ]

        reasons: list[str] = []
        eligible = True
        if days_since > window_days:
            eligible = False
            reasons.append(f"outside the {window_days}-day window ({days_since} days since transaction)")
        if existing:
            eligible = False
            reasons.append(f"already has an active dispute: {existing[0]['dispute_id']}")
        if eligible:
            reasons.append(f"within the {window_days}-day window ({days_since} days since transaction)")

        return {
            "transaction_id": transaction_id,
            "reason": reason,
            "eligible": eligible,
            "window_days": window_days,
            "days_since_transaction": days_since,
            "explanation": reasons,
        }


_REASON_TO_WINDOW_KEY = {
    "unrecognized_charge": "unauthorized_transaction_days",
    "unauthorized_transaction": "unauthorized_transaction_days",
    "duplicate_charge": "duplicate_charge_days",
    "goods_not_received": "goods_not_received_days",
    "billing_error": "billing_error_days",
}

# Dispute-window reference policy (served as an MCP resource).
DISPUTE_WINDOWS = {
    "unauthorized_transaction_days": 60,
    "duplicate_charge_days": 90,
    "goods_not_received_days": 120,
    "billing_error_days": 60,
    "note": "Synthetic servicing reference. Windows are measured from the "
    "transaction posting date.",
}
