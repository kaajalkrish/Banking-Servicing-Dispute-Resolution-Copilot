"""Tests for the tool-scope gateway (AC-06, defense-in-depth)."""

from __future__ import annotations

from src.tools.gateway import ScopeGatewayTool


class _OkTool:
    name = "get_account_balance"

    async def ainvoke(self, args):
        return {"balance": 100, "customer_id_seen": args.get("customer_id")}


class _NoCustomerIdTool:
    name = "get_dispute_status"

    async def ainvoke(self, args):
        return {"status": "open"}


async def test_matching_customer_id_passes_through():
    tool = ScopeGatewayTool(_OkTool(), authenticated_customer_id="C0001")
    result = await tool.ainvoke({"customer_id": "C0001"})
    assert result == {"balance": 100, "customer_id_seen": "C0001"}


async def test_mismatched_customer_id_is_denied():
    tool = ScopeGatewayTool(_OkTool(), authenticated_customer_id="C0001")
    result = await tool.ainvoke({"customer_id": "C0002"})
    assert result["ok"] is False
    assert result["error"]["reason_code"] == "cross_customer_scope_violation"


async def test_denial_callback_fires_with_the_right_arguments():
    denials = []
    tool = ScopeGatewayTool(
        _OkTool(),
        authenticated_customer_id="C0001",
        on_denied=lambda name, auth, req: denials.append((name, auth, req)),
    )
    await tool.ainvoke({"customer_id": "C0002"})
    assert denials == [("get_account_balance", "C0001", "C0002")]


async def test_tool_without_customer_id_arg_is_unaffected():
    tool = ScopeGatewayTool(_NoCustomerIdTool(), authenticated_customer_id="C0001")
    result = await tool.ainvoke({"dispute_id": "DSP001"})
    assert result == {"status": "open"}
