"""Compare two golden-signals reports and write the measured before/after
delta (§8.1 optimization note, P5-15).

Reads two golden_signals.json-shaped reports (baseline and optimized) and
diffs latency-by-class p50/p95. The aggregate latency_by_class numbers mix
every worker (supervisor, product_info, account_servicing, ...) and every
retry attempt however the two reports were generated -- too noisy to
attribute to the one code path that actually changed (P5-13's dispute-worker
concurrency). So this also re-queries each report's own Phoenix project
(recorded in the report itself) for the isolated latency of just the
`dispute` span: the direct, honest measurement of the actual change, not
diluted by unrelated worker/retry traffic.

Usage:
    python scripts/compare_reports.py \
        --baseline reports/golden_signals_baseline_dispute.json \
        --optimized reports/golden_signals_optimized_dispute.json \
        --span-name dispute \
        --out reports/optimization_comparison.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Windows terminals often default to a non-UTF-8 codepage; get_all_spans()
# below calls init_tracing() -> Phoenix's launch_app(), which unconditionally
# prints an emoji and crashes on cp1252 otherwise (same real bug found and
# fixed in src/observability/golden_signals.py).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latency_by_class_delta(baseline: dict[str, Any], optimized: dict[str, Any]) -> dict[str, Any]:
    """p50/p95 delta per span class present in both reports (optimized - baseline;
    negative means optimized is faster)."""
    delta: dict[str, Any] = {}
    classes = set(baseline.get("latency_by_class", {})) & set(optimized.get("latency_by_class", {}))
    for cls in sorted(classes):
        b = baseline["latency_by_class"][cls]
        o = optimized["latency_by_class"][cls]
        delta[cls] = {
            "baseline_p50_ms": b["p50_ms"],
            "optimized_p50_ms": o["p50_ms"],
            "p50_delta_ms": o["p50_ms"] - b["p50_ms"],
            "baseline_p95_ms": b["p95_ms"],
            "optimized_p95_ms": o["p95_ms"],
            "p95_delta_ms": o["p95_ms"] - b["p95_ms"],
        }
    return delta


def worker_span_latency(project: str, span_name: str) -> dict[str, Any]:
    """Isolate one worker's own span latency for a project: real per-span
    durations from Phoenix, not the mixed aggregate every worker and every
    retry attempt contributes to."""
    from src.observability.export import get_all_spans

    df = get_all_spans(project)
    spans = df[df["name"] == span_name].copy()
    if spans.empty:
        return {"project": project, "span_name": span_name, "count": 0}
    spans["latency_ms"] = (spans["end_time"] - spans["start_time"]).dt.total_seconds() * 1000.0
    lat = spans["latency_ms"]
    return {
        "project": project,
        "span_name": span_name,
        "count": int(len(lat)),
        "mean_ms": float(lat.mean()),
        "median_ms": float(lat.median()),
        "min_ms": float(lat.min()),
        "max_ms": float(lat.max()),
    }


def build_comparison(
    baseline: dict[str, Any], optimized: dict[str, Any], *, baseline_path: str, optimized_path: str, span_name: str
) -> dict[str, Any]:
    baseline_span = worker_span_latency(baseline["project"], span_name)
    optimized_span = worker_span_latency(optimized["project"], span_name)
    median_delta = None
    if baseline_span.get("count") and optimized_span.get("count"):
        median_delta = optimized_span["median_ms"] - baseline_span["median_ms"]

    return {
        "baseline_report": baseline_path,
        "optimized_report": optimized_path,
        "baseline_project": baseline["project"],
        "optimized_project": optimized["project"],
        "latency_by_class_delta": latency_by_class_delta(baseline, optimized),
        "worker_span_latency": {
            "span_name": span_name,
            "baseline": baseline_span,
            "optimized": optimized_span,
            "median_delta_ms": median_delta,
        },
        "tokens": {"baseline": baseline.get("tokens"), "optimized": optimized.get("tokens")},
        "span_count": {"baseline": baseline.get("span_count"), "optimized": optimized.get("span_count")},
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline", required=True, help="path to the baseline golden_signals report")
    p.add_argument("--optimized", required=True, help="path to the optimized golden_signals report")
    p.add_argument("--span-name", default="dispute", help="the changed worker's span name, isolated for a direct comparison")
    p.add_argument("--out", default="reports/optimization_comparison.json")
    args = p.parse_args(argv)

    baseline = _load(Path(args.baseline))
    optimized = _load(Path(args.optimized))
    comparison = build_comparison(
        baseline, optimized, baseline_path=args.baseline, optimized_path=args.optimized, span_name=args.span_name
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(comparison, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"compare_reports: wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
