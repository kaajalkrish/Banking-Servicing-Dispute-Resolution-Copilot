"""Command-line interface — the single documented command that runs the copilot.

Commands:
  chat     --customer-id C0001 [--thread-id T] [--message "..."]
  run      --inputs data/sample_inputs/conversations.jsonl
  mcp-demo                       exercise the MCP tools (no LLM) -> transcript

Output is masked; the process exits non-zero on failure. Later phases add
`export`, `regenerate`, `eval` and `redteam` subcommands.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from src.common.masking import mask_text
from src.config import settings

# Windows terminals often default to a non-UTF-8 codepage; Gemini responses can
# include en-dashes/emoji that would otherwise mangle into "?" or raise on write.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _print(text: str) -> None:
    print(mask_text(text))


# --------------------------------------------------------------------------- #
# mcp-demo  (no LLM required)
# --------------------------------------------------------------------------- #
async def cmd_mcp_demo(_args: argparse.Namespace) -> int:
    from src.mcp_client import get_client, get_dispute_windows, get_mcp_tools
    from src.observability.tracing import flush_tracing, init_tracing

    init_tracing()  # called on the run path (not merely imported), P3-05

    client = get_client()
    tools = await get_mcp_tools(client)
    by_name = {t.name: t for t in tools}
    _print(f"MCP tools: {sorted(by_name)}")

    cid = "C0001"
    # A representative sequence exercising every tool + the resource read.
    calls = [
        ("get_account_balance", {"customer_id": cid}),
        ("list_recent_transactions", {"customer_id": cid, "limit": 3}),
        ("get_statement_summary", {"customer_id": cid}),
        ("submit_service_request", {"customer_id": cid, "request_type": "statement_copy"}),
        ("get_dispute_status", {"dispute_id": "DSP00001"}),
    ]
    for name, args in calls:
        tool = by_name.get(name)
        if tool is None:
            _print(f"[skip] {name} not available")
            continue
        result = await tool.ainvoke(args)
        _print(f"{name}({args}) -> {result}")

    windows = await get_dispute_windows(client)
    _print(f"resource bank://reference/dispute-windows -> {windows[:80]}...")
    _print("mcp-demo complete; transcript at logs/mcp_transcript.jsonl")
    flush_tracing()
    return 0


# --------------------------------------------------------------------------- #
# chat / run  (require Gemini)
# --------------------------------------------------------------------------- #
async def _answer_for(out: dict[str, Any]) -> str:
    fa = out.get("final_answer") or {}
    ans = fa.get("answer", "(no answer)")
    if fa.get("requires_human_review"):
        ans += "  [flagged for human review]"
    return ans


async def cmd_chat(args: argparse.Namespace) -> int:
    from src.common.ids import new_run_id
    from src.graph import build_graph, open_checkpointer, run_config
    from src.llm import get_llm
    from src.memory.long_term import build_extractor, open_memory_store
    from src.observability.tracing import flush_tracing, init_tracing, traced_run
    from src.state import new_state

    settings.require_api_key()  # fail fast with a clear message if unset
    init_tracing()  # called before graph execution (not merely imported), P3-05
    tools = await _load_tools()
    thread_id = args.thread_id or f"chat-{args.customer_id}"
    worker_llm = get_llm("default")

    async with open_checkpointer() as saver, open_memory_store() as mstore:
        graph = build_graph(
            supervisor_llm=get_llm("fast"),
            worker_llm=worker_llm,
            tools=tools,
            checkpointer=saver,
            memory_store=mstore,
            memory_extractor=build_extractor(worker_llm, mstore),
        )

        async def turn(text: str) -> None:
            # One run_id per turn (D-04): the finest useful granularity for a
            # later failure citation to point at exactly which turn failed.
            run_id = new_run_id()
            with traced_run(run_id):
                out = await graph.ainvoke(
                    new_state(args.customer_id, text, max_steps=settings.max_steps),
                    run_config(thread_id),
                )
            _print("copilot> " + await _answer_for(out))

        if args.message:
            await turn(args.message)
            flush_tracing()
            return 0

        _print(f"Chat as {args.customer_id} (thread {thread_id}). Type 'exit' to quit.")
        while True:
            try:
                text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in {"exit", "quit"}:
                break
            if text:
                await turn(text)
    flush_tracing()
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    from src.common.ids import new_run_id
    from src.graph import build_graph, open_checkpointer, run_config
    from src.llm import get_llm
    from src.memory.long_term import build_extractor, open_memory_store
    from src.observability.tracing import flush_tracing, init_tracing, traced_run
    from src.state import new_state

    settings.require_api_key()
    init_tracing()  # called before graph execution (not merely imported), P3-05
    path = Path(args.inputs)
    if not path.exists():
        _print(f"inputs file not found: {path}")
        return 1
    conversations = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tools = await _load_tools()
    worker_llm = get_llm("default")

    async with open_checkpointer() as saver, open_memory_store() as mstore:
        graph = build_graph(
            supervisor_llm=get_llm("fast"),
            worker_llm=worker_llm,
            tools=tools,
            checkpointer=saver,
            memory_store=mstore,
            memory_extractor=build_extractor(worker_llm, mstore),
        )
        for conv in conversations:
            cid = conv["customer_id"]
            thread_id = conv.get("conversation_id", f"run-{cid}")
            _print(f"\n=== {thread_id} ({cid}) ===")
            for text in conv.get("turns", []):
                _print(f"you> {text}")
                run_id = new_run_id()
                with traced_run(run_id):
                    out = await graph.ainvoke(
                        new_state(cid, text, max_steps=settings.max_steps),
                        run_config(thread_id),
                    )
                _print("copilot> " + await _answer_for(out))
    flush_tracing()
    return 0


async def cmd_regenerate(args: argparse.Namespace) -> int:
    """Regenerate committed evidence from the sample conversations (NFR-02,
    §3.4 Reproducibility Rule). Default output is artifacts_regen/
    (gitignored); --commit-evidence writes the canonical traces/ and logs/
    paths instead (D-06). --keep-ui leaves the Phoenix server running
    afterwards so a dashboard screenshot can be taken (P5)."""
    import os

    from src.observability.export import export_project

    if not args.traces:
        _print("regenerate: pass --traces to regenerate the trace export (eval is added in Phase 5)")
        return 1

    inputs_path = args.inputs or "data/sample_inputs/conversations.jsonl"

    if args.commit_evidence:
        log_dir = Path("logs")
        parquet_path = Path("traces/phoenix_spans.parquet")
    else:
        out_dir = Path("artifacts_regen")
        log_dir = out_dir / "logs"
        parquet_path = out_dir / "traces" / "phoenix_spans.parquet"
    log_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LOG_DIR"] = str(log_dir)  # picked up by mcp transcript + tool logging (read fresh, not cached)

    exit_code = await cmd_run(argparse.Namespace(inputs=inputs_path))
    if exit_code != 0:
        return exit_code

    df = export_project(settings.phoenix_project, parquet_path=parquet_path)
    _print(f"regenerate: exported {len(df)} spans -> {parquet_path}")
    _print(f"regenerate: logs written under {log_dir}/")

    if args.keep_ui:
        _print("Phoenix UI running at http://localhost:6006 -- press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            pass

    return 0


async def cmd_export(args: argparse.Namespace) -> int:
    from src.observability.export import export_project

    project = args.project or settings.phoenix_project
    parquet_path = Path(args.parquet) if args.parquet else None
    csv_path = Path(args.csv) if args.csv else None
    if parquet_path is None and csv_path is None:
        parquet_path = Path("traces/phoenix_spans.parquet")  # canonical default (§7.2)

    df = export_project(project, parquet_path=parquet_path, csv_path=csv_path)
    _print(f"exported {len(df)} spans for project {project!r}")
    if parquet_path is not None:
        _print(f"  parquet -> {parquet_path}")
    if csv_path is not None:
        _print(f"  csv -> {csv_path}")
    return 0


async def _load_tools() -> list[Any]:
    from src.llm import get_llm
    from src.mcp_client import get_mcp_tools
    from src.tools.rag_tool import PolicySearchTool

    mcp_tools = await get_mcp_tools()
    rag_tool = PolicySearchTool(llm=get_llm("default"))
    return [*mcp_tools, rag_tool]


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="src.cli", description="Banking servicing copilot CLI")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("chat", help="chat with the copilot")
    c.add_argument("--customer-id", required=True)
    c.add_argument("--thread-id", default=None)
    c.add_argument("--message", default=None, help="one-shot message (non-interactive)")
    c.set_defaults(func=cmd_chat)

    r = sub.add_parser("run", help="run a batch of sample conversations")
    r.add_argument("--inputs", required=True)
    r.set_defaults(func=cmd_run)

    g = sub.add_parser("regenerate", help="regenerate committed evidence from sample conversations")
    g.add_argument("--traces", action="store_true", help="regenerate the trace export (required for now)")
    g.add_argument("--inputs", default=None, help="default: data/sample_inputs/conversations.jsonl")
    g.add_argument(
        "--commit-evidence", action="store_true",
        help="write to the canonical traces/ and logs/ paths instead of artifacts_regen/",
    )
    g.add_argument("--keep-ui", action="store_true", help="leave the Phoenix UI running afterwards")
    g.set_defaults(func=cmd_regenerate)

    e = sub.add_parser("export", help="export Phoenix spans to parquet/csv")
    e.add_argument("--project", default=None, help="Phoenix project name (default: PHOENIX_PROJECT)")
    e.add_argument("--parquet", default=None, help="output parquet path (default: traces/phoenix_spans.parquet)")
    e.add_argument("--csv", default=None, help="output csv path (optional)")
    e.set_defaults(func=cmd_export)

    d = sub.add_parser("mcp-demo", help="exercise the MCP tools and write the transcript")
    d.set_defaults(func=cmd_mcp_demo)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(args.func(args))
    except RuntimeError as exc:  # e.g. missing API key
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
