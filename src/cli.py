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


def _print(text: str) -> None:
    print(mask_text(text))


# --------------------------------------------------------------------------- #
# mcp-demo  (no LLM required)
# --------------------------------------------------------------------------- #
async def cmd_mcp_demo(_args: argparse.Namespace) -> int:
    from src.mcp_client import get_client, get_dispute_windows, get_mcp_tools

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
    from src.graph import build_graph, open_checkpointer, run_config
    from src.llm import get_llm
    from src.state import new_state

    settings.require_api_key()  # fail fast with a clear message if unset
    tools = await _load_tools()
    thread_id = args.thread_id or f"chat-{args.customer_id}"

    async with open_checkpointer() as saver:
        graph = build_graph(
            supervisor_llm=get_llm("fast"),
            worker_llm=get_llm("default"),
            tools=tools,
            checkpointer=saver,
        )

        async def turn(text: str) -> None:
            out = await graph.ainvoke(
                new_state(args.customer_id, text, max_steps=settings.max_steps),
                run_config(thread_id),
            )
            _print("copilot> " + await _answer_for(out))

        if args.message:
            await turn(args.message)
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
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    from src.graph import build_graph, open_checkpointer, run_config
    from src.llm import get_llm
    from src.state import new_state

    settings.require_api_key()
    path = Path(args.inputs)
    if not path.exists():
        _print(f"inputs file not found: {path}")
        return 1
    conversations = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tools = await _load_tools()

    async with open_checkpointer() as saver:
        graph = build_graph(
            supervisor_llm=get_llm("fast"),
            worker_llm=get_llm("default"),
            tools=tools,
            checkpointer=saver,
        )
        for conv in conversations:
            cid = conv["customer_id"]
            thread_id = conv.get("conversation_id", f"run-{cid}")
            _print(f"\n=== {thread_id} ({cid}) ===")
            for text in conv.get("turns", []):
                _print(f"you> {text}")
                out = await graph.ainvoke(
                    new_state(cid, text, max_steps=settings.max_steps),
                    run_config(thread_id),
                )
                _print("copilot> " + await _answer_for(out))
    return 0


async def _load_tools() -> list[Any]:
    from src.mcp_client import get_mcp_tools

    return await get_mcp_tools()


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
