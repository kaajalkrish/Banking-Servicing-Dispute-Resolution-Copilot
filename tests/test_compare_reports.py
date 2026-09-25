"""Tests for the optimization-note comparison script's pure logic (P5-15, §8.1).

worker_span_latency() queries real Phoenix data and is exercised by running
the script directly against the two committed golden-signals reports (see
the evidence commit), not duplicated here.
"""

from __future__ import annotations

import scripts.compare_reports as cr


def _report(project: str, **classes: dict) -> dict:
    return {"project": project, "latency_by_class": classes}


def test_latency_delta_reports_negative_for_a_faster_optimized_run():
    baseline = _report("b", acting={"p50_ms": 100.0, "p95_ms": 200.0})
    optimized = _report("o", acting={"p50_ms": 60.0, "p95_ms": 120.0})
    delta = cr.latency_by_class_delta(baseline, optimized)
    assert delta["acting"]["p50_delta_ms"] == -40.0
    assert delta["acting"]["p95_delta_ms"] == -80.0


def test_latency_delta_only_covers_classes_present_in_both():
    baseline = _report("b", acting={"p50_ms": 1.0, "p95_ms": 2.0}, tool={"p50_ms": 1.0, "p95_ms": 2.0})
    optimized = _report("o", acting={"p50_ms": 1.0, "p95_ms": 2.0})
    delta = cr.latency_by_class_delta(baseline, optimized)
    assert set(delta) == {"acting"}


def test_build_comparison_computes_median_delta(monkeypatch):
    monkeypatch.setattr(
        cr,
        "worker_span_latency",
        lambda project, span_name: {
            "project": project,
            "span_name": span_name,
            "count": 5,
            "mean_ms": 100.0,
            "median_ms": 90.0 if project == "b" else 70.0,
            "min_ms": 10.0,
            "max_ms": 200.0,
        },
    )
    baseline = _report("b", acting={"p50_ms": 1.0, "p95_ms": 2.0})
    optimized = _report("o", acting={"p50_ms": 1.0, "p95_ms": 2.0})
    comparison = cr.build_comparison(
        baseline, optimized, baseline_path="b.json", optimized_path="o.json", span_name="dispute"
    )
    assert comparison["worker_span_latency"]["median_delta_ms"] == -20.0
    assert comparison["baseline_project"] == "b"
    assert comparison["optimized_project"] == "o"


def test_build_comparison_median_delta_is_none_without_span_data(monkeypatch):
    monkeypatch.setattr(
        cr, "worker_span_latency", lambda project, span_name: {"project": project, "span_name": span_name, "count": 0}
    )
    baseline = _report("b", acting={"p50_ms": 1.0, "p95_ms": 2.0})
    optimized = _report("o", acting={"p50_ms": 1.0, "p95_ms": 2.0})
    comparison = cr.build_comparison(
        baseline, optimized, baseline_path="b.json", optimized_path="o.json", span_name="dispute"
    )
    assert comparison["worker_span_latency"]["median_delta_ms"] is None
