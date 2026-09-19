"""Export Phoenix spans to parquet and CSV (§7.2 Trace export, §8).

Reads spans from the persisted ``.phoenix/`` working directory — relaunching
the local Phoenix app if this is a fresh process, since spans persisted by an
earlier CLI invocation are only servable once a Phoenix app is running
against that same working directory again (verified: a fresh process
launching against the same directory correctly served spans written by an
earlier, already-exited process).

Handles nested/dict-valued columns (Phoenix's spans dataframe includes
columns like ``attributes.metadata``, a dict per row) by JSON-stringifying
them before writing — parquet and CSV can't natively store Python dicts/lists
in a cell.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.observability.tracing import PHOENIX_URL, get_client, init_tracing


def _stringify_nested_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].apply(lambda v: isinstance(v, (dict, list))).any():
            out[col] = out[col].apply(
                lambda v: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v
            )
    return out


def get_all_spans(project_name: str, *, limit: int = 100_000) -> pd.DataFrame:
    """Fetch all spans for a project as a dataframe, ready for export."""
    init_tracing(project_name)  # ensures a Phoenix app is running against .phoenix/
    client = get_client(PHOENIX_URL)
    return client.spans.get_spans_dataframe(project_name=project_name, limit=limit)


def export_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _stringify_nested_columns(df).to_parquet(path)


def export_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _stringify_nested_columns(df).to_csv(path, index=True)


def export_project(
    project_name: str,
    *,
    parquet_path: Path | None = None,
    csv_path: Path | None = None,
) -> pd.DataFrame:
    """Fetch and export a project's spans to whichever paths are given."""
    df = get_all_spans(project_name)
    if parquet_path is not None:
        export_parquet(df, parquet_path)
    if csv_path is not None:
        export_csv(df, csv_path)
    return df
