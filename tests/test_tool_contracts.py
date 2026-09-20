"""Tool-contract tests for every MCP tool (§7.6, §8 Agent tests, AC-06).

For each tool: assert its input JSON schema (required fields), the shape of a
successful output, and at least one error path returns a structured error.
Offline, no network — calls the server's tool functions directly.
"""

from __future__ import annotations

import pytest

from mcp_server import server as srv
from src.tools.rag_index import get_collection
from src.tools.rag_tool import PolicySearchTool

# Required input fields per tool (matches mcp_server/server.py signatures).
REQUIRED_FIELDS = {
    "get_account_balance": {"customer_id"},
    "list_recent_transactions": {"customer_id"},
    "get_statement_summary": {"customer_id"},
    "create_dispute_case": {"customer_id", "transaction_id", "reason"},
    "get_dispute_status": {"dispute_id"},
    "submit_service_request": {"customer_id", "request_type"},
    "check_dispute_eligibility": {"customer_id", "transaction_id", "reason"},
}


def _a_customer_with_one_account():
    """Return (customer_id, account_ref) for a single-account customer."""
    counts: dict[str, int] = {}
    for a in srv._bank.accounts:
        counts[a["customer_id"]] = counts.get(a["customer_id"], 0) + 1
    for a in srv._bank.accounts:
        if counts[a["customer_id"]] == 1:
            return a["customer_id"], a["account_number"][-4:]
    # fallback: any customer, pass explicit ref
    a = srv._bank.accounts[0]
    return a["customer_id"], a["account_number"][-4:]


@pytest.mark.parametrize("tool_name, required", REQUIRED_FIELDS.items())
def test_input_schema_declares_required_fields(tool_input_schemas, tool_name, required):
    schema = tool_input_schemas[tool_name]
    assert schema["type"] == "object"
    declared_required = set(schema.get("required", []))
    assert required <= declared_required, (
        f"{tool_name}: expected required {required}, schema has {declared_required}"
    )
    # every required field is declared as a property with a type
    for field in required:
        assert field in schema["properties"], f"{tool_name} missing property {field}"


def test_balance_output_shape():
    cid, ref = _a_customer_with_one_account()
    out = srv.get_account_balance(cid, ref)
    assert set(["account_ref", "balance", "currency", "status"]) <= set(out)
    assert isinstance(out["balance"], (int, float))
    # never a full account/card number in the output
    assert "card_number" not in out and "account_number" not in out


def test_recent_transactions_output_shape():
    cid, ref = _a_customer_with_one_account()
    out = srv.list_recent_transactions(cid, ref, limit=5)
    assert "transactions" in out and isinstance(out["transactions"], list)
    assert out["count"] == len(out["transactions"])
    assert out["count"] <= 5


def test_statement_summary_output_shape():
    cid, ref = _a_customer_with_one_account()
    out = srv.get_statement_summary(cid, ref)
    assert isinstance(out["by_category"], dict)
    assert isinstance(out["total_spend"], (int, float))


def test_create_dispute_is_draft_only():
    cid = srv._bank.accounts[0]["customer_id"]
    acct = srv._bank.accounts[0]["account_number"]
    txn = next(t for t in srv._bank.transactions if t["account_number"] == acct)
    out = srv.create_dispute_case(cid, txn["transaction_id"], "duplicate_charge")
    assert out["status"] == "draft"  # D-13: never auto-resolved
    assert out["dispute_id"].startswith("DSP")


def test_submit_service_request_output_shape():
    cid = srv._bank.accounts[0]["customer_id"]
    out = srv.submit_service_request(cid, "card_replacement")
    assert out["status"] == "received"
    assert out["request_id"].startswith("SR")


def test_check_dispute_eligibility_output_shape():
    cid = srv._bank.accounts[0]["customer_id"]
    acct = srv._bank.accounts[0]["account_number"]
    txn = next(t for t in srv._bank.transactions if t["account_number"] == acct)
    out = srv.check_dispute_eligibility(cid, txn["transaction_id"], "unrecognized_charge")
    assert set(["eligible", "window_days", "days_since_transaction", "explanation"]) <= set(out)
    assert isinstance(out["eligible"], bool)
    assert isinstance(out["explanation"], list)


def test_get_dispute_status_output_shape():
    dispute_id = next(iter(srv._bank._disputes))  # a seeded dispute
    out = srv.get_dispute_status(dispute_id)
    assert {"dispute_id", "transaction_id", "reason", "status", "opened_date"} <= set(out)
    assert out["dispute_id"] == dispute_id
    assert isinstance(out["status"], str)
    # never an account or card number in the output
    assert "card_number" not in out and "account_number" not in out


# --- error paths (structured error objects, not exceptions) ---

def test_error_unknown_dispute():
    out = srv.get_dispute_status("DSP-DOES-NOT-EXIST")
    assert "error" in out and out["error"]["type"] == "LookupError"


def test_error_invalid_service_request_type():
    cid = srv._bank.accounts[0]["customer_id"]
    out = srv.submit_service_request(cid, "wire_transfer_to_stranger")
    assert "error" in out and out["error"]["type"] == "ValueError"


def test_error_dispute_on_foreign_transaction():
    """A customer cannot dispute a transaction that is not theirs."""
    cid = srv._bank.accounts[0]["customer_id"]
    other_txn = next(
        t for t in srv._bank.transactions
        if t["account_number"] != srv._bank.accounts[0]["account_number"]
    )
    out = srv.create_dispute_case(cid, other_txn["transaction_id"], "unrecognized_charge")
    assert "error" in out and out["error"]["type"] == "PermissionError"


def test_error_check_dispute_eligibility_bad_reason():
    cid = srv._bank.accounts[0]["customer_id"]
    acct = srv._bank.accounts[0]["account_number"]
    txn = next(t for t in srv._bank.transactions if t["account_number"] == acct)
    out = srv.check_dispute_eligibility(cid, txn["transaction_id"], "i just feel like it")
    assert "error" in out and out["error"]["type"] == "ValueError"


# --- agentic-RAG tool contract (policy_search): input/output schema + abstention ---


class _FakeAnswerLLM:
    """Offline stand-in: composes a fixed answer, never calls an LLM grader
    (real distance thresholds decide confident/poor for these test queries)."""

    async def ainvoke(self, _messages):
        from langchain_core.messages import AIMessage

        return AIMessage(content="The overdraft fee is $30 [POL-FEES §Overdraft Fee].")


class _FakeOutOfScopeRewriteLLM:
    """Stand-in whose 'rewrite' also stays out of corpus, so the abstention
    path doesn't accidentally self-fulfill into a match (a plain fixed-answer
    fake would return fee-related text, which the rewrite step would then use
    as the NEXT query and could spuriously match POL-FEES)."""

    async def ainvoke(self, _messages):
        from langchain_core.messages import AIMessage

        return AIMessage(content="home mortgage refinancing interest rates")


@pytest.fixture(scope="module")
def rag_tool():
    return PolicySearchTool(collection=get_collection(), llm=_FakeAnswerLLM())


async def test_policy_search_input_output_schema(rag_tool):
    out = await rag_tool.ainvoke({"query": "what is the overdraft fee"})
    assert set(["answer", "citations", "abstained"]) <= set(out)
    assert isinstance(out["citations"], list)
    assert isinstance(out["abstained"], bool)
    for c in out["citations"]:
        assert set(["doc_id", "section"]) <= set(c)


async def test_policy_search_abstains_on_out_of_corpus_topic():
    tool = PolicySearchTool(collection=get_collection(), llm=_FakeOutOfScopeRewriteLLM())
    out = await tool.ainvoke({"query": "what is my mortgage interest rate"})
    assert out["abstained"] is True
    assert out["citations"] == []
