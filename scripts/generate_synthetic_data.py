"""Deterministic synthetic banking-data generator (stdlib only).

Produces customers, accounts (with Luhn-valid synthetic PANs on a reserved test
BIN), transactions and a small dispute seed. All data is synthetic (ref-doc.md
§3.4, NFR-05, §6.2 no real data). A fixed seed makes every run and test use
identical data.

Design notes:
- Account numbers use an ``AC`` prefix + 10 digits so they are never bare digit
  runs in free text and are only exposed via masked, key-tagged fields.
- PANs use a reserved synthetic BIN (400000) and a real Luhn check digit, so the
  guardrail/PII recognisers have realistic-but-fake numbers to detect.
- Transactions deliberately include duplicates, foreign-currency and
  unrecognised-merchant items, which make good dispute scenarios (AC-02).

Usage:
    python scripts/generate_synthetic_data.py --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"

SYNTHETIC_BIN = "400000"  # reserved, non-issuer test prefix (clearly synthetic)
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "INR"]
KNOWN_MERCHANTS = [
    "Whole Foods", "Shell", "Netflix", "Uber", "Amazon", "Starbucks",
    "Delta Airlines", "AT&T", "Costco", "Spotify",
]
# Merchants a customer is unlikely to recognise -> good dispute candidates.
SUSPICIOUS_MERCHANTS = [
    "GLBL-DIGITAL-SVCS", "QUICKPAY LTD", "XYZ*TECH", "PROMO-CLUB-99", "NOVA MEDIA INT",
]
CATEGORIES = ["groceries", "fuel", "subscription", "travel", "dining", "retail", "utilities"]


def luhn_check_digit(base: str) -> str:
    """Return the Luhn check digit for a numeric base string."""
    digits = [int(c) for c in base]
    total = 0
    # base will be followed by the check digit, so parity is computed accordingly.
    parity = (len(base) + 1) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - (total % 10)) % 10)


def make_pan(rng: random.Random) -> str:
    middle = "".join(str(rng.randint(0, 9)) for _ in range(15 - len(SYNTHETIC_BIN)))
    base = SYNTHETIC_BIN + middle  # 15 digits
    return base + luhn_check_digit(base)  # 16-digit, Luhn-valid


def make_customers(rng: random.Random, n: int) -> list[dict]:
    first = ["Ava", "Liam", "Noah", "Emma", "Olivia", "Ethan", "Mia", "Lucas"]
    last = ["Stone", "Rivera", "Chen", "Patel", "Kowalski", "Okafor", "Nguyen", "Brooks"]
    customers = []
    for i in range(1, n + 1):
        fn = rng.choice(first)
        ln = rng.choice(last)
        cid = f"C{i:04d}"
        customers.append(
            {
                "customer_id": cid,
                "name": f"{fn} {ln}",
                "email": f"{fn.lower()}.{ln.lower()}@example.test",
                "authenticated": True,
            }
        )
    return customers


def make_accounts(rng: random.Random, customers: list[dict]) -> list[dict]:
    accounts = []
    seq = 1000000000
    for c in customers:
        for _ in range(rng.randint(1, 2)):
            acct_no = f"AC{seq + rng.randint(0, 8999999):010d}"[:12]
            accounts.append(
                {
                    "account_number": acct_no,
                    "customer_id": c["customer_id"],
                    "type": rng.choice(["checking", "savings"]),
                    "currency": "USD",
                    "balance": round(rng.uniform(150.0, 12500.0), 2),
                    "card_number": make_pan(rng),
                    "status": "active",
                }
            )
            seq += 1
    return accounts


def make_transactions(rng: random.Random, accounts: list[dict]) -> list[dict]:
    txns = []
    tid = 1
    today = date(2026, 9, 1)
    for acct in accounts:
        count = rng.randint(10, 18)
        for _ in range(count):
            days_ago = rng.randint(0, 120)
            is_suspicious = rng.random() < 0.15
            is_foreign = rng.random() < 0.15
            merchant = (
                rng.choice(SUSPICIOUS_MERCHANTS) if is_suspicious else rng.choice(KNOWN_MERCHANTS)
            )
            currency = rng.choice([c for c in CURRENCIES if c != "USD"]) if is_foreign else "USD"
            txns.append(
                {
                    "transaction_id": f"TXN{tid:07d}",
                    "account_number": acct["account_number"],
                    "date": (today - timedelta(days=days_ago)).isoformat(),
                    "amount": round(rng.uniform(3.5, 950.0), 2),
                    "currency": currency,
                    "merchant": merchant,
                    "category": rng.choice(CATEGORIES),
                    "status": rng.choice(["posted", "posted", "posted", "pending"]),
                    "unrecognized": is_suspicious,
                }
            )
            tid += 1
        # Inject an exact duplicate of the last transaction (classic dispute case).
        if txns:
            dup = dict(txns[-1])
            dup["transaction_id"] = f"TXN{tid:07d}"
            dup["duplicate_of"] = txns[-1]["transaction_id"]
            txns.append(dup)
            tid += 1
    return txns


def make_disputes_seed(rng: random.Random, txns: list[dict]) -> list[dict]:
    candidates = [t for t in txns if t.get("unrecognized") or t.get("duplicate_of")]
    rng.shuffle(candidates)
    disputes = []
    for i, t in enumerate(candidates[:3], start=1):
        disputes.append(
            {
                "dispute_id": f"DSP{i:05d}",
                "transaction_id": t["transaction_id"],
                "account_number": t["account_number"],
                "reason": "unrecognized_charge" if t.get("unrecognized") else "duplicate_charge",
                "status": rng.choice(["open", "under_review"]),
                "opened_date": t["date"],
            }
        )
    return disputes


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic banking data.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--customers", type=int, default=5)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    customers = make_customers(rng, args.customers)
    accounts = make_accounts(rng, customers)
    transactions = make_transactions(rng, accounts)
    disputes = make_disputes_seed(rng, transactions)

    datasets = {
        "customers.json": customers,
        "accounts.json": accounts,
        "transactions.json": transactions,
        "disputes_seed.json": disputes,
    }
    for name, data in datasets.items():
        (OUT_DIR / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(data)} records")


if __name__ == "__main__":
    main()
