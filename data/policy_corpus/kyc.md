---
doc_id: POL-KYC
title: Know Your Customer (KYC) and Identity Verification Policy
version: 1.0
effective_date: 2026-01-01
---

# Know Your Customer (KYC) and Identity Verification Policy

## Identity Verification at Servicing
Before discussing account details, the copilot verifies the customer is
authenticated for the account in question. No balance, transaction, or
account-holder information for a different customer is ever provided,
regardless of how the request is phrased.

## Re-Verification Triggers
Re-verification (a short identity challenge) is required before high-risk
actions: a large wire transfer, adding a new external payee, or changing the
contact email or phone number on file.

## Recordkeeping
Identity documents and verification records are retained for 7 years after
account closure, consistent with the bank's regulatory obligations.

## Data Minimization
Only the information necessary for the specific servicing request is
accessed or displayed; full account and card numbers are masked in all
customer-facing responses and internal logs.

## Suspicious Activity
Signs of identity misuse (e.g., a request that does not match the
authenticated customer's own account) are declined and flagged for a human
agent to review, rather than acted upon by the copilot.
