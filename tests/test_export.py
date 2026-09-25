"""Tests for the Phoenix span export helpers (§7.2 Trace export, §8).

Only the pure dataframe-transform logic is tested offline (no network/server);
the full export path (real Phoenix app + client) is verified live, not in the
default suite, per D-11.
"""

from __future__ import annotations

import json

import pandas as pd

from src.observability.export import _stringify_nested_columns


def test_dict_valued_column_is_json_stringified():
    df = pd.DataFrame({"attributes.metadata": [{"run_id": "run-123"}, {"run_id": "run-456"}]})
    out = _stringify_nested_columns(df)
    assert all(isinstance(v, str) for v in out["attributes.metadata"])
    assert json.loads(out["attributes.metadata"].iloc[0]) == {"run_id": "run-123"}


def test_plain_columns_are_left_unchanged():
    df = pd.DataFrame({"name": ["ChatGoogleGenerativeAI"], "latency_ms": [12.3]})
    out = _stringify_nested_columns(df)
    pd.testing.assert_frame_equal(out, df)


def test_list_valued_column_is_json_stringified():
    df = pd.DataFrame({"events": [[{"name": "start"}], []]})
    out = _stringify_nested_columns(df)
    assert all(isinstance(v, str) for v in out["events"])
