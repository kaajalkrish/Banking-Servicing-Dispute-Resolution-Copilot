"""Tests for span-kind classification (D-05, §7.3).

Assertions are pinned to the real span_kind distribution observed from two
live graph runs (see the P3-04 commit body): 9 CHAIN, 2 LLM, 1 TOOL for a
balance query; 14 CHAIN, 2 LLM for a RAG-answered fee question. No network.
"""

from __future__ import annotations

import pandas as pd

from src.observability.span_types import classify_span_kind, classify_spans_dataframe


def test_llm_maps_to_thinking():
    assert classify_span_kind("LLM") == "thinking"
    assert classify_span_kind("llm") == "thinking"  # case-insensitive


def test_tool_and_retriever_map_to_tool():
    assert classify_span_kind("TOOL") == "tool"
    assert classify_span_kind("RETRIEVER") == "tool"


def test_chain_and_agent_map_to_acting():
    assert classify_span_kind("CHAIN") == "acting"
    assert classify_span_kind("AGENT") == "acting"


def test_unknown_or_missing_kind_defaults_to_acting():
    assert classify_span_kind(None) == "acting"
    assert classify_span_kind("SOMETHING_UNKNOWN") == "acting"


def test_classify_spans_dataframe_matches_real_observed_distribution():
    """Pinned to real captured spans from a live balance-query graph run:
    9 CHAIN (LangGraph, supervisor, account_servicing, finalize, ...),
    2 LLM (routing + answer composition), 1 TOOL (get_account_balance)."""
    df = pd.DataFrame({"span_kind": ["CHAIN"] * 9 + ["LLM"] * 2 + ["TOOL"] * 1})
    out = classify_spans_dataframe(df)
    assert out["span_class"].value_counts().to_dict() == {"acting": 9, "thinking": 2, "tool": 1}
