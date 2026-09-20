# Delivery Runbook: Transfer, Push and Pull Requests

How to get this repository from the personal laptop onto the Git host at the
office and merge the six phase branches by pull request. It follows
`plan.md` sections 4.7 and 4.8 and Appendix C, with the real branch names.

Roles: **A** is Kaajal Krishnamurthy, **B** is Akash Saranathan. Whoever is at
the keyboard sets their own identity on the office laptop (step 3).

The rules that matter (ref-doc NFR-07): at least three pull-request merges
using a **merge commit** (`git merge --no-ff`), and **no direct pushes to
`main`** after the root commit. Never squash, never rebase-merge, never delete
the phase branches.

## 1. Before leaving the personal laptop

Run from the repository root on the last commit of `phase-6/governance-delivery-bonus`.

```bash
git status                                   # nothing to commit; see the note on .claude/ below
pytest -q -m "not live"                      # offline suite; never run without -m "not live"
python scripts/verify_submission.py          # every ref-doc section 7 row (run --check-git-merges later, on the remote)
python scripts/verify_citations.py           # every citation and CTL id resolves
python scripts/check_secrets.py              # no secrets in the tree or history
python scripts/scan_evidence_for_pii.py      # no plaintext PAN or account number in evidence
find . -path ./.venv -prune -o \( -iname 'Dockerfile*' -o -iname 'docker-compose*' \) -print   # must print nothing
git log --oneline -- ref-doc.md              # exactly one commit
```

Commit-trailer and author checks (plan section 4.4), run per phase:

```bash
git log phase-5/evaluation-cost-governance..HEAD --format=%H | while read h; do
  git show -s --format=%B "$h" | grep -q '^Co-authored-by: ' || echo "MISSING TRAILER: $h"
done
git log phase-5/evaluation-cost-governance..HEAD --reverse --format='%h %an | %cn | %s'   # authors alternate
```

Notes:

- `.claude/` (a local tool directory) shows up as untracked. It is not part of
  the history and a bundle ignores it; delete it or leave it, but do not add it.
- The evidence PII scan reads the whole `reports/dashboard_data.csv` (96 MB)
  and takes a few seconds; that is expected.
- `pytest -q -m "not live"` must be run once before delivery; earlier commits
  were tested with only the affected test files.

## 2. Transfer

**Option 1, recommended: a git bundle** (history only, so no secret can travel).

```bash
cd <repo-folder>
git status
git bundle create ../hackathon.bundle --all
git bundle verify ../hackathon.bundle
# carry hackathon.bundle (optionally zipped) to the office laptop
```

**Option 2: zip the folder.** The zip must include the hidden `.git` folder and
must exclude `.env` (it holds the API key), `.venv/`, `.phoenix/`,
`data/chroma/`, `data/state/`, `artifacts_regen/`, `__pycache__/`,
`.pytest_cache/`, `.deepeval/` and any model cache.

```bash
# from the parent directory of the repo, in Git Bash
zip -r hackathon.zip <repo-folder> \
   -x "*/.env" "*/.venv/*" "*/.phoenix/*" "*/data/chroma/*" "*/data/state/*" \
      "*/artifacts_regen/*" "*/__pycache__/*" "*/.pytest_cache/*" "*/.deepeval/*"
```

## 3. Restore on the office laptop

```bash
git clone hackathon.bundle hackathon-repo && cd hackathon-repo
for b in $(git branch -r | grep -v 'HEAD' | sed 's#origin/##'); do git branch --track "$b" "origin/$b" 2>/dev/null; done
git branch -a                    # expect main plus the six phase branches below
git remote remove origin         # origin currently points at the bundle file
git config user.name "<your name>"; git config user.email "<your email>"
```

From a zip instead: unzip, `cd` into the folder, and check `git status`,
`git branch -a` and `git log --oneline --graph --all --decorate | head -50`.

The branches, each created from the tip of the one before it:

| Phase | Branch | Created from |
|---|---|---|
| 1 | `phase-1/foundation-graph-mcp` | `main` |
| 2 | `phase-2/context-memory-rag` | `phase-1/foundation-graph-mcp` |
| 3 | `phase-3/observability-tracing` | `phase-2/context-memory-rag` |
| 4 | `phase-4/security-guardrails-audit` | `phase-3/observability-tracing` |
| 5 | `phase-5/evaluation-cost-governance` | `phase-4/security-guardrails-audit` |
| 6 | `phase-6/governance-delivery-bonus` | `phase-5/evaluation-cost-governance` |

## 4. Push and merge

Prerequisite: an **empty** repository on the Git host (no README, no licence),
so the first push is clean.

```bash
git remote add origin <REMOTE_URL>
git push -u origin main         # 1) main first: the root commit only
```

**[MANUAL, M-9]** Now turn on branch protection for `main`: "Require a pull
request before merging", 0 required approvals, and do **not** enable
"Automatically delete head branches".

Then for each phase N = 1 to 6, strictly in order:

1. Push the branch: `git push -u origin <branch>`.
2. Open a pull request with base `main` and compare `<branch>`, using the
   title and body for that phase in section 5.
3. Merge it with **Create a merge commit** (this is `git merge --no-ff`), using
   the merge subject and body from section 5.
4. `git checkout main && git pull origin main` and confirm the merge commit is
   there before pushing the next branch.

Rules:

- Wait until PR N is merged before pushing branch N+1, so each PR shows only
  its own commits.
- Alternate who clicks merge: PR 1 A, PR 2 B, PR 3 A, PR 4 B, PR 5 A, PR 6 B.
  Put both names in the merge commit body.
- GitHub CLI equivalent: `gh pr create --base main --head <branch> --title "<title>" --body-file <file>`,
  then `gh pr merge <number> --merge --subject "<merge subject>" --body "<merge body>"`.
  On GitLab or Azure DevOps choose the merge-commit / no-fast-forward strategy.
- Never push to `main` directly after the root; never squash or rebase-merge;
  do not delete phase branches.

## 5. Pull request titles, bodies and merge commits

Each body starts with a `@COUNT@` placeholder. Fill it from the branch with
`git rev-list --count <base>..<branch>` (base is `main` for PR 1, the previous
phase branch for the others; after each merge `main` contains it), for example:

```bash
N=$(git rev-list --count main..phase-1/foundation-graph-mcp)
sed "s/@COUNT@/$N/" pr1.md > pr1.final.md
```

| PR | Title | Merge commit subject | Merger |
|---|---|---|---|
| 1 | `Phase 1: Foundation — data, MCP server, LangGraph graph, CLI` | `merge(phase-1): foundation — data, MCP server, LangGraph graph, CLI (#1)` | A |
| 2 | `Phase 2: Context engineering, tiered memory and agentic RAG` | `merge(phase-2): context engineering, tiered memory, agentic RAG (#2)` | B |
| 3 | `Phase 3: Observability — Phoenix tracing, tool log, trace export` | `merge(phase-3): Phoenix observability, tool log, trace export (#3)` | A |
| 4 | `Phase 4: Security — guardrails, audit trail, Presidio, red-team` | `merge(phase-4): guardrails, audit trail, Presidio, red-team (#4)` | B |
| 5 | `Phase 5: Evaluation, golden signals, cost governance, failure analysis` | `merge(phase-5): evaluation, golden signals, cost governance, failures (#5)` | A |
| 6 | `Phase 6: Governance pack, FastAPI bonus, runbook and verification` | `merge(phase-6): governance pack, FastAPI bonus, runbook, verification (#6)` | B |

Merge commit body (paste into the merge dialog; fill the angle brackets):

```
Phase N complete: <goal>.
Covers: <AC/NFR ids and §7/§8 rows>.
Commits: <count>. Evidence: <key paths>.
Merged by <A or B>; co-developed by Kaajal Krishnamurthy and Akash Saranathan.
```

### PR 1 body: `pr1.md`

```markdown
## Phase 1 — Foundation: data, MCP server, LangGraph graph, CLI
Branch: `phase-1/foundation-graph-mcp` → `main` · Commits: @COUNT@

### Requirements covered (ref-doc.md)
- §3: balance/transaction queries, dispute intake, simple service requests; typed state, supervisor routing to intake / account-servicing / dispute / product-info workers, conditional routing, checkpointing, structured output; custom MCP server (7 tools + 1 resource) consumed through langchain-mcp-adapters.
- §3.4 rules: Synthetic-Data (seeded generator, masking), Gemini-only (LLM factory), Evidence-in-Repo (MCP transcript produced by committed code).
- §5: AC-01, AC-04, AC-02 (capture part), AC-06 (masking foundation); NFR-01, NFR-02, NFR-04, NFR-05, NFR-06.
- §7: LangGraph graph, MCP server, secrets hygiene, routing / loop-guard / tool-contract tests, README skeleton.

### Evidence added
| Path | Produced by |
|---|---|
| `data/synthetic/*.json` | `python scripts/generate_synthetic_data.py --seed 42` |
| `logs/mcp_transcript.jsonl` | `python -m src.cli mcp-demo` |

### How it was verified
Offline suite green at the end of the phase (`pytest -q -m "not live"`, 31 tests); a live batch over the 10 sample conversations of the time ran cleanly.

### Notes
Live testing found and fixed four real issues (a transient-error crash, Gemini 3.x content format, a Windows console codepage, service-request routing); they are separate commits on the branch.
```

### PR 2 body: `pr2.md`

```markdown
## Phase 2 — Context engineering, tiered memory and agentic RAG
Branch: `phase-2/context-memory-rag` → `main` · Commits: @COUNT@

### Requirements covered (ref-doc.md)
- §3: product and fee questions grounded in policy, remembering context; engineered context (write / select / compress / isolate, summarization, quarantine of untrusted text), tiered memory, agentic-RAG tool.
- §5: AC-02 (eligibility against policy), AC-03 (cited answer, abstains when unsupported), AC-05 (in-conversation facts and return-visit recall), AC-04, AC-06 (quarantine); NFR-03, NFR-04, NFR-05, NFR-06.
- §7: context engineering, tiered memory (`src/memory/`, `tests/test_memory_persistence.py`, `logs/memory_test.log`), agentic-RAG tool and policy corpus; tool-contract test extended.

### Evidence added
| Path | Produced by |
|---|---|
| `data/policy_corpus/` | committed synthetic corpus; index built by `python scripts/build_policy_index.py` |
| `logs/memory_test.log` | `pytest tests/test_memory_persistence.py -m live -q` |

### How it was verified
Offline suite green (40 tests at the end of the phase); full pipeline run live with Gemini, LangMem and Chroma over the 14 sample conversations, including abstention and cross-session recall.

### Notes
A live run exposed that `product_info` discarded recalled memory when RAG abstained; fixed and re-verified live.
```

### PR 3 body: `pr3.md`

```markdown
## Phase 3 — Observability: Arize Phoenix tracing, tool log, trace export
Branch: `phase-3/observability-tracing` → `main` · Commits: @COUNT@

### Requirements covered (ref-doc.md)
- §3: "fully traced"; Phoenix instrumentation with a committed trace export and a machine-generated tool-invocation log.
- §3.4: Evidence-in-Repo, Citation-Resolves prerequisites (run_id stamped on every span), Reproducibility (regenerate command).
- §5: AC-07 (tool log, names reconcile with code); NFR-02, NFR-04, NFR-05, NFR-06.
- §7: Phoenix instrumentation (`src/observability/tracing.py`), trace export, tool-invocation log.

### Evidence added
| Path | Produced by |
|---|---|
| `logs/tool_calls.jsonl` | `python -m src.cli regenerate --traces --commit-evidence` |
| `traces/phoenix_spans.parquet` | same command, then `python scripts/verify_trace_export.py` (replaced by a fuller export in phase 5) |
| `reports/tool_reconciliation.json` | `python scripts/verify_tool_names.py` |

### How it was verified
Offline suite green (75 tests at the end of the phase); a full 14-conversation run traced end to end; trace-export and tool-name verifiers pass.

### Notes
`arize-phoenix` is pinned to 14.6.0 because a newer release upgrades `mcp` to 2.x and breaks the MCP server. `ref-doc.md`'s `px.Client()` does not exist in that version; the real client API is used and documented.
```

### PR 4 body: `pr4.md`

```markdown
## Phase 4 — Security: guardrails, audit trail, Presidio, red-team
Branch: `phase-4/security-guardrails-audit` → `main` · Commits: @COUNT@

### Requirements covered (ref-doc.md)
- §3: guardrailed against injection and PII leakage, auditable; input and output guardrails, audit trail, secrets hygiene, output-risk classification code and human-review gate.
- §5: AC-06, AC-10, AC-02 / AC-04 (gating, refusal); NFR-01, NFR-03, NFR-05, NFR-06.
- §7: guardrail code, audit trail, secrets hygiene. §8.1: Presidio PII-redaction sample and a red-team attack set with results.

### Evidence added
| Path | Produced by |
|---|---|
| `logs/agent_actions.jsonl` | `python -m src.cli regenerate --traces --commit-evidence` |
| `reports/redteam_results.json`, `docs/redteam-results.md` | `python -m src.cli redteam` |
| `reports/pii_redaction_sample.json` | `python scripts/pii_redaction_sample.py` |
| `reports/secrets_scan.json` | `python scripts/check_secrets.py` |

### How it was verified
Offline suite green (145 tests at the end of the phase); red-team 37/37 (4 documented known gaps counted as accepted); full 14-conversation guarded run with real denials in the audit trail.

### Notes
Six real bugs found and fixed while building it (for example the "ignore all previous instructions" pattern missing chained qualifiers, and system-prompt leaks being flagged but not removed); the encoded-payload gaps are documented, not hidden.
```

### PR 5 body: `pr5.md`

```markdown
## Phase 5 — Evaluation, golden signals, cost governance, failure analysis
Branch: `phase-5/evaluation-cost-governance` → `main` · Commits: @COUNT@

### Requirements covered (ref-doc.md)
- §3: cost- and latency-governed, continuously evaluated; DeepEval with a Gemini judge; Phoenix-derived golden signals and dashboard; evidence-linked failure analysis.
- §5: AC-08 (three real failures with run ids, root cause, fix), AC-09 (latency by thinking / acting / tool, tokens, cost estimate, accuracy, hallucination rate; dashboard screenshot and data), AC-12 (evaluation report; agent tests).
- §7: failure analysis, golden signals, dashboard, evaluation report with harness.

### Evidence added
| Path | Produced by |
|---|---|
| `reports/eval_report.json`, `reports/eval_report_initial.json` | `python -m src.cli eval --limit 30 --out <path>` |
| `reports/golden_signals.json` | `python -m src.observability.golden_signals --eval reports/eval_report_initial.json --out reports/golden_signals.json` |
| `reports/dashboard_data.csv`, `traces/phoenix_spans.parquet` | `python -m src.cli export --csv …` / `--parquet …` |
| `reports/dashboard.png` | screenshot of the local Phoenix UI |
| `docs/failure-analysis.md`, `reports/citation_check.json` | hand-written; `python scripts/verify_citations.py` |

### How it was verified
Offline tests green for the code in this phase; citations verified. `reports/golden_signals.json` carries a real cost estimate ($0.44 at paid list price, from prices read from Google's published page).

### Notes
- The scored evaluation covers the first 30 of the 47 authored golden cases: a full run exceeded a free-tier daily quota. `ref-doc.md` sets no minimum size.
- `reports/eval_report.json` is the run made **before** the three documented fixes (accuracy 0.6); it has not been re-scored.
- The optional baseline/optimized comparison (ref-doc §8.1 Good-to-Have) was deferred and is not included.
```

### PR 6 body: `pr6.md`

```markdown
## Phase 6 — Governance pack, FastAPI bonus, runbook and verification
Branch: `phase-6/governance-delivery-bonus` → `main` · Commits: @COUNT@

### Requirements covered (ref-doc.md)
- §3: governed for compliance; governance pack, reproducible runbook; every rule re-verified.
- §5: AC-11 (risk register, model card, compliance mapping to EU AI Act / NIST AI RMF / DPDP, each citing committed controls); NFR-02, NFR-07.
- §7: risk register, model / system card, compliance mapping, output-risk classification, local-run runbook, git workflow, FastAPI bonus (`src/api/`).

### Evidence added
| Path | Produced by |
|---|---|
| `docs/architecture.md`, `docs/control-catalog.md`, `docs/risk-register.md`, `docs/model-card.md`, `docs/compliance.md`, `docs/security-approach.md`, `docs/delivery-runbook.md` | hand-written; checked by `python scripts/verify_citations.py` |
| `reports/pii_scan.json` | `python scripts/scan_evidence_for_pii.py` |

### How it was verified
`python scripts/verify_submission.py`, `python scripts/verify_citations.py`, `pytest -q -m "not live"` (paste the results here).

### Notes
Before opening this PR, edit "Evidence added" and "Notes" to match the branch: state whether the output-risk sample and document, the API demo log and the optional optimization note were produced, and if not, say so plainly. Gaps in `docs/compliance.md` (DPDP notice, consent, erasure; AI Act Art. 50(2)) are deliberate and documented.
```

## 6. Verify on the remote clone

After all six merges:

```bash
git log --first-parent --oneline main            # root + 6 merges
git log --merges --oneline | wc -l               # at least 6
git log --first-parent --format='%h %p %s' main  # every non-root line lists TWO parents
python scripts/verify_submission.py --check-git-merges
```

Then repeat the section 1 checks (offline tests, verifiers, scans) once on the
office laptop. To work on the remote clone, reinstall from `requirements.txt`
and recreate `.env` from `.env.example`; neither the key nor `.venv` travels.

## 7. Manual steps

| ID | Step | When |
|---|---|---|
| M-7 | Transfer the bundle or zip to the office laptop | section 2 |
| M-8 | Push and merge the branches by pull request | section 4 |
| M-9 | Enable branch protection on `main` after the first push | section 4 |
