"""Golden-signals report (§7.3, §8 Golden-signals report).

Reads a Phoenix project's spans, computes p50/p95 latency split by
thinking/acting/tool (D-05, src/observability/span_types.py), token totals
from LLM spans, a cost estimate (src/observability/pricing.py -- published
list prices with source URL and date; omitted, not fabricated, for any model
without a confirmed price), an error rate and
request count, and imports accuracy + hallucination_rate from an already-
produced eval report (reports/eval_report.json by default). Writes
reports/golden_signals.json.

CLI: python -m src.observability.golden_signals [--project P] [--eval PATH]
     [--out PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.observability.export import get_all_spans
from src.observability.pricing import (
    CONFIRMED_ON,
    PRICE_BASIS,
    SOURCE_URL,
    PriceNotConfirmedError,
    estimate_cost_usd,
)
from src.observability.span_types import classify_span_kind


def _latency_ms(df: pd.DataFrame) -> pd.Series:
    return (df["end_time"] - df["start_time"]).dt.total_seconds() * 1000.0


def _percentile_by_class(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    df = df.copy()
    df["span_class"] = df["span_kind"].apply(classify_span_kind)
    df["latency_ms"] = _latency_ms(df)
    out: dict[str, dict[str, float]] = {}
    for cls, group in df.groupby("span_class"):
        lat = group["latency_ms"].dropna()
        if lat.empty:
            continue
        out[cls] = {
            "p50_ms": float(lat.quantile(0.50)),
            "p95_ms": float(lat.quantile(0.95)),
            "count": int(len(lat)),
        }
    return out


def _token_totals(df: pd.DataFrame) -> dict[str, int]:
    llm = df[df["span_kind"] == "LLM"]
    prompt = llm.get("attributes.llm.token_count.prompt")
    completion = llm.get("attributes.llm.token_count.completion")
    return {
        "input_tokens": int(prompt.fillna(0).sum()) if prompt is not None else 0,
        "output_tokens": int(completion.fillna(0).sum()) if completion is not None else 0,
        "llm_call_count": int(len(llm)),
    }


def _cost_usd(df: pd.DataFrame, token_totals: dict[str, int]) -> dict[str, Any]:
    llm = df[df["span_kind"] == "LLM"]
    model_col = llm.get("attributes.llm.model_name")
    models = sorted({m for m in (model_col.dropna().unique().tolist() if model_col is not None else [])})
    if not models:
        return {"total_usd": None, "note": "no LLM spans found", "models": []}
    total = 0.0
    per_model: dict[str, float] = {}
    unconfirmed: list[str] = []
    for model in models:
        rows = llm[llm["attributes.llm.model_name"] == model]
        in_tok = int(rows["attributes.llm.token_count.prompt"].fillna(0).sum())
        out_tok = int(rows["attributes.llm.token_count.completion"].fillna(0).sum())
        try:
            cost = estimate_cost_usd(model, input_tokens=in_tok, output_tokens=out_tok)
        except PriceNotConfirmedError:
            unconfirmed.append(model)
            continue
        per_model[model] = cost
        total += cost
    if unconfirmed:
        return {
            "total_usd": None,
            "note": f"price not confirmed for: {', '.join(unconfirmed)} (see src/observability/pricing.py, [MANUAL] M-3)",
            "models": models,
            "per_model_usd": per_model or None,
        }
    return {
        "total_usd": total,
        "per_model_usd": per_model,
        "models": models,
        "price_source_url": SOURCE_URL,
        "prices_confirmed_on": CONFIRMED_ON,
        "basis": PRICE_BASIS,
    }


def _error_rate(df: pd.DataFrame) -> dict[str, Any]:
    total = len(df)
    errors = int((df["status_code"] != "OK").sum()) if "status_code" in df.columns else 0
    return {
        "request_count": total,
        "error_count": errors,
        "error_rate": (errors / total) if total else 0.0,
    }


def compute_golden_signals(
    project_name: str, *, eval_report_path: Path | None = None
) -> dict[str, Any]:
    df = get_all_spans(project_name)
    report: dict[str, Any] = {
        "project": project_name,
        "span_count": int(len(df)),
        "latency_by_class": _percentile_by_class(df),
        "tokens": _token_totals(df),
        "request_volume": _error_rate(df),
    }
    tokens = report["tokens"]
    report["cost"] = _cost_usd(df, tokens)

    if eval_report_path is not None and eval_report_path.exists():
        eval_data = json.loads(eval_report_path.read_text(encoding="utf-8"))
        metrics = eval_data.get("metrics", {})
        report["accuracy"] = metrics.get("accuracy")
        report["hallucination_rate"] = metrics.get("hallucination_rate")
        report["eval_report_source"] = str(eval_report_path)
    else:
        report["accuracy"] = None
        report["hallucination_rate"] = None
        report["eval_report_source"] = None

    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compute golden signals from a Phoenix project's spans")
    p.add_argument("--project", default=None, help="Phoenix project name (default: PHOENIX_PROJECT)")
    p.add_argument("--eval", default="reports/eval_report.json", help="eval report to pull accuracy/hallucination_rate from")
    p.add_argument("--out", default="reports/golden_signals.json")
    args = p.parse_args(argv)

    from src.config import settings

    project = args.project or settings.phoenix_project
    report = compute_golden_signals(project, eval_report_path=Path(args.eval))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"golden_signals: wrote {out_path} ({report['span_count']} spans)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
