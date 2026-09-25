"""Tests for the citation verifier (§3.4 Citation-Resolves Rule, AC-08, AC-11).

Fully offline: every case builds a tiny fake repo under tmp_path.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import scripts.verify_citations as v

_CATALOG = """# Control Catalog

| ID | Control | Code path (symbol) | Evidence artifact |
|---|---|---|---|
| CTL-01 | Input guard | `src/guard.py` (`check_input`) | `reports/guard.json` |
| CTL-02 | Output guard | `src/out.py` (`sanitize`, `_helper`) | `reports/guard.json` (`action=sanitize`) |
"""


def _repo(tmp_path: Path, *, catalog: str = _CATALOG) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "guard.py").write_text("def check_input(): ...\n", encoding="utf-8")
    (tmp_path / "src" / "out.py").write_text("def sanitize(): ...\ndef _helper(): ...\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "guard.json").write_text("{}", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "control-catalog.md").write_text(catalog, encoding="utf-8")
    return tmp_path


def _check(root: Path, *docs: str) -> dict:
    return v.verify_citations(
        [root / d for d in docs],
        traces_path=root / "none.parquet",
        log_paths=[root / "none.jsonl"],
        catalog_path=root / "docs" / "control-catalog.md",
        root=root,
    )


def _kinds(result: dict) -> list[str]:
    return [f["kind"] for f in result["unresolved"]]


def test_parse_control_catalog_reads_each_row(tmp_path):
    controls = v.parse_control_catalog(_repo(tmp_path) / "docs" / "control-catalog.md")
    assert set(controls) == {"CTL-01", "CTL-02"}
    assert controls["CTL-01"]["code"] == "`src/guard.py` (`check_input`)"


def test_clean_catalog_and_doc_pass(tmp_path):
    root = _repo(tmp_path)
    (root / "docs" / "risk.md").write_text(
        "Mitigated by CTL-01 (`src/guard.py`), evidence `reports/guard.json`.", encoding="utf-8"
    )
    result = _check(root, "docs/risk.md")
    assert result["ok"], result["unresolved"]
    assert result["controls_checked"] == 2


def test_missing_symbol_in_catalog_is_flagged(tmp_path):
    root = _repo(tmp_path)
    (root / "src" / "out.py").write_text("def sanitize(): ...\n", encoding="utf-8")  # _helper gone
    result = _check(root)
    assert {"kind": "ctl_symbol", "doc": str(root / "docs" / "control-catalog.md"), "value": "CTL-02: _helper"} in result[
        "unresolved"
    ]


def test_missing_code_and_evidence_paths_are_flagged(tmp_path):
    root = _repo(tmp_path)
    (root / "src" / "guard.py").unlink()
    (root / "reports" / "guard.json").unlink()
    kinds = _kinds(_check(root))
    assert "ctl_code_path" in kinds
    assert "ctl_evidence" in kinds


def test_control_row_with_no_evidence_is_flagged(tmp_path):
    catalog = _CATALOG + "| CTL-03 | Naked | `src/guard.py` (`check_input`) | see the code |\n"
    result = _check(_repo(tmp_path, catalog=catalog))
    assert any(f["value"] == "CTL-03: no evidence" for f in result["unresolved"])


def test_doc_citing_unknown_control_is_flagged(tmp_path):
    root = _repo(tmp_path)
    (root / "docs" / "risk.md").write_text("Mitigated by CTL-01 and CTL-99.", encoding="utf-8")
    result = _check(root, "docs/risk.md")
    assert [f["value"] for f in result["unresolved"]] == ["CTL-99"]


def test_doc_citing_missing_repo_path_is_flagged_but_globs_and_dirs_resolve(tmp_path):
    root = _repo(tmp_path)
    (root / "docs" / "risk.md").write_text(
        "See `src/nope.py`, `reports/*.json`, `src/` and `bank://reference/x`.", encoding="utf-8"
    )
    result = _check(root, "docs/risk.md")
    assert [(f["kind"], f["value"]) for f in result["unresolved"]] == [("repo_path", "src/nope.py")]


def test_path_with_symbol_or_line_suffix_resolves_to_the_file(tmp_path):
    root = _repo(tmp_path)
    (root / "docs" / "risk.md").write_text("`src/guard.py::check_input` and `src/guard.py:1-3`", encoding="utf-8")
    assert _check(root, "docs/risk.md")["ok"]


def test_missing_doc_is_flagged(tmp_path):
    assert _kinds(_check(_repo(tmp_path), "docs/absent.md")) == ["missing_doc"]


def test_run_id_in_a_log_resolves_and_an_unknown_one_does_not(tmp_path):
    root = _repo(tmp_path)
    good = "run-2acadb2c-16af-49f6-9baa-80d20767fcd5"
    bad = "run-00000000-0000-4000-8000-000000000000"
    (root / "logs").mkdir()
    (root / "logs" / "tool_calls.jsonl").write_text(json.dumps({"run_id": good}) + "\n", encoding="utf-8")
    (root / "docs" / "fa.md").write_text(f"{good} and {bad}", encoding="utf-8")
    result = v.verify_citations(
        [root / "docs" / "fa.md"],
        traces_path=root / "none.parquet",
        log_paths=[root / "logs" / "tool_calls.jsonl"],
        catalog_path=None,
        root=root,
    )
    assert [(f["kind"], f["value"]) for f in result["unresolved"]] == [("run_id", bad)]


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_untracked_or_gitignored_file_does_not_count_as_committed(tmp_path):
    root = _repo(tmp_path)
    (root / "notes").mkdir()
    (root / "notes" / "scratch.local.md").write_text("private", encoding="utf-8")
    (root / "docs" / "risk.md").write_text("Evidence: `notes/scratch.local.md` and `reports/guard.json`.", encoding="utf-8")
    _git(root, "init", "-q")
    (root / ".gitignore").write_text("notes/*.local.md\n", encoding="utf-8")
    _git(root, "add", "-A")
    result = _check(root, "docs/risk.md")
    assert [(f["kind"], f["value"]) for f in result["unresolved"]] == [("repo_path", "notes/scratch.local.md")]


def test_commit_subject_in_evidence_must_exist_in_history(tmp_path):
    subject = "fix(llm): retry transient errors"
    catalog = _CATALOG + f"| CTL-03 | Retry | `src/guard.py` (`check_input`) | commit history (`{subject}`) |\n"
    root = _repo(tmp_path, catalog=catalog)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    assert any(f["value"].startswith("CTL-03: commit") for f in _check(root)["unresolved"])
    _git(root, "commit", "-q", "-m", subject)
    assert _check(root)["ok"]
