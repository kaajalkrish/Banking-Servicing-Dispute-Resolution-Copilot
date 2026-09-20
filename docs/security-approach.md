# Security Approach: Authentication, Secrets and Incident Handling

Banking Servicing & Dispute-Resolution Copilot (BC-AAIE-HACK-01).

**Status: described, not implemented.** The brief (`ref-doc.md`, section 6.2)
puts advanced OAuth flows and live secrets-rotation infrastructure out of
scope and asks for the approach to be documented instead. This document is
that description. Nothing here is code, and no control below should be read
as present in the repository unless section 1 says so.

## 1. What exists today

| Concern | Current behaviour | Where |
|---|---|---|
| Who the customer is | The CLI takes `--customer-id` and treats it as already authenticated. It is placed in graph state once and never read from request text | `src/cli.py`, `src/state.py` |
| Cross-customer access | Every tool call is checked against the authenticated id in state; a mismatch is denied and audited | `src/tools/gateway.py` (CTL-05) |
| Secrets | The only secret is the Gemini API key. It is read from an environment variable; `.env` is gitignored; `.env.example` holds placeholders | `src/config.py`, `.env.example`, `.gitignore` |
| Secret leakage | A scanner checks the working tree and the full git history; masking keeps account numbers out of logs | `scripts/check_secrets.py`, `reports/secrets_scan.json` (CTL-17, CTL-07) |
| Audit | Consequential actions are logged with the customer id hashed | `src/guardrails/audit.py` (CTL-10) |

The key gap is the first row: there is no real authentication. The
authorization logic downstream of it (scope enforcement) is sound only if the
id it receives is trustworthy (risk R-04 in `docs/risk-register.md`).

## 2. Customer authentication in production

**Goal:** the graph's authenticated customer id must come from a verified
credential issued by the bank's identity provider, never from anything the
customer or the model can type.

1. **Sign-in with OpenID Connect.** The customer signs in to the bank's app
   or site through the bank's identity provider using the OAuth 2.0
   authorization code flow (RFC 6749) with PKCE (RFC 7636), which is the right
   flow for public clients such as a mobile app or browser. The chat client
   then sends the resulting access token with each request. The copilot never
   sees the customer's password.
2. **Short-lived, signed access tokens.** Access tokens are JWTs (RFC 7519,
   profiled by RFC 9068) with a short lifetime, issued for the copilot API as
   the audience. The API validates signature, issuer, audience and expiry on
   every request, using the identity provider's published keys.
3. **Identity mapping.** A stable customer reference from the token (the
   subject claim) is mapped to the internal customer id, and that value is the
   only thing written into graph state. This is the existing design: the
   gateway already trusts state and ignores request text, so the change is
   confined to where state's customer id comes from.
4. **Token scoping.** Each token carries narrow scopes, for example
   `accounts:read`, `disputes:draft`, `service-requests:create`. The tool
   layer checks the scope before a tool runs, on top of the customer-id check,
   so a token issued for read-only use cannot draft a dispute.
5. **Step-up for sensitive actions.** Drafting a dispute or a service request
   requires a recent strong authentication (for example a second factor within
   the last few minutes); otherwise the copilot asks the customer to
   re-authenticate before proceeding.
6. **Backend calls.** When a real core-banking system replaces the synthetic
   MCP server, the copilot calls it with credentials of its own (client
   credentials with mutual TLS) and passes the customer context along using
   token exchange (RFC 8693), so the backend can enforce its own per-customer
   authorization and the copilot never holds a broad-privilege user token.
7. **Tokens never reach the model or the logs.** Access tokens are kept out of
   prompts, out of tool arguments, out of Phoenix spans and out of the
   audit and tool logs; the masking and evidence-scanning controls
   (CTL-07, CTL-18) would be extended to recognise bearer tokens.

**Why it is not implemented here.** There is no identity provider and no real
customer; a locally faked OAuth flow would only give a false sense of
assurance. The graph's trust boundary (customer id from state only) is built
so that real authentication can be added without changing the guardrails.

## 3. Secrets management and rotation in production

Today's only secret is the Gemini API key; a production system would add a
database credential, signing keys and backend client credentials, and the
same approach covers all of them.

- **Storage.** Secrets live in a managed secret store backed by a key
  management service, injected into the process at start-up. They are not
  kept in `.env` files on disk, in container images, in the repository or in
  build logs. `.env` and `.env.example` remain the development convention.
- **Least privilege.** Each secret is scoped to one purpose and one
  environment. The model-provider key is limited to the one API it is needed
  for, and to the service's network egress where the provider supports
  restricting a key that way. Development and production use different keys.
- **Rotation without downtime.** Rotate on a schedule, and immediately on
  suspected exposure or when someone with access leaves: create a new key,
  deploy it alongside the old one, confirm traffic is healthy on the new key,
  then revoke the old one. Because keys are read from configuration at
  start-up, rotation is a redeploy, not a code change.
- **Detection.** The existing scanner (CTL-17) runs in continuous integration
  and as a pre-commit check so a leaked key is caught before it reaches the
  history. If one is found in history, the key is treated as compromised and
  rotated first; rewriting history is secondary.
- **Audit.** Access to the secret store is itself logged and reviewed.

## 4. Incident and breach handling (approach)

Referenced from `docs/compliance.md` (DPDP Act section 8(6)). Not built.

1. **Detect.** Signals include repeated scope denials or other-customer
   attempts in the audit trail, guardrail block spikes, secrets-scanner hits
   and unusual tool-call volume in the tool log.
2. **Contain.** Revoke the affected tokens or rotate the affected secrets
   (section 3); disable the affected tool or route if needed.
3. **Assess.** Use the audit trail and Phoenix traces, which are keyed by
   `run_id`, to establish which customers and which data were involved.
4. **Notify.** Where personal data is involved, notify the regulator and each
   affected customer in the form and manner the law prescribes. The DPDP
   rules that set this were not reviewed for this project, so the exact
   content and deadlines are left to counsel.
5. **Learn.** Record the incident in the same form as
   `docs/failure-analysis.md`: symptom, evidence, root cause, fix.

## 5. Retention and erasure (approach)

Referenced from `docs/compliance.md` (DPDP Act sections 8(7) and 12). Not built.

- **Logs and traces** get a fixed retention period, after which they are
  deleted; the period is set by legal and operational need.
- **Long-term memory** is stored per customer in its own namespace
  (`customer_namespace` in `src/memory/long_term.py`), so erasing one
  customer's remembered facts is a single-namespace delete, and a customer
  correcting a remembered fact is an edit within it. That design choice is what
  makes an erasure or correction feature practical to add.
- The audit trail records the customer id only as a hash, so erasing a
  customer's data does not require rewriting the audit trail.

## 6. Residual risk

Until real authentication, secret-store injection and the incident and
erasure processes exist, the system must not be connected to real customer
data (risks R-04, R-13, R-16, R-17 in `docs/risk-register.md`).
