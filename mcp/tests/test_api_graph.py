"""실제 Graph → MCP HTTP → Spring HTTP 어댑터 계약을 연결한다. Spring 응답만 대체한다."""

from copy import deepcopy
import asyncio
import json

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from unlockops.contracts import validate_output
from unlockops.graph import build_graph
from unlockops.models import Plan
from unlockops.rules import source_hashes
from unlockops_mcp import business
from unlockops_mcp.backend_client import BackendClient
from unlockops_mcp.policy import mcp as policy_mcp
from test_http import rpc
from test_backend_client import CONTEXT, EMPLOYEE, PROFILE, RESOURCE, PROBLEM


def test_api_backed_tools_wait_for_approval_then_execute_and_verify(monkeypatch):
    calls, held = [], {"role": None}
    resource = {"id": RESOURCE, "external_id": "payment-core", "name": "payment-core", "platform": "GITHUB", "access_scope": "TF"}

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        if request.url.path == "/internal/resources/resolve":
            return httpx.Response(200, json={"matches": [resource], "ambiguous": False})
        if request.url.path == "/internal/access-context":
            context = {**deepcopy(CONTEXT), "source_hashes": source_hashes(), "profile": PROFILE,
                "current": {"role": held["role"]}, "membership": {"member": True, "leader_id": "leader"}}
            return httpx.Response(200, json=context)
        if request.url.path.endswith("/grant"):
            assert json.loads(request.content) == {"idempotencyKey": "approved-key"}
            held["role"] = "Write"
            return httpx.Response(200, json={"ok": True, "changed": True, "role": "Write"})
        if request.url.path == "/internal/access-verifications":
            return httpx.Response(200, json={"ok": True, "verified": held["role"] == "Write", "current": {"role": held["role"]}})
        raise AssertionError(request.url.path)

    monkeypatch.setattr(business, "repo", BackendClient(httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="http://backend:8080", token="test-internal-token"))
    with rpc(business.mcp) as business_rpc, rpc(policy_mcp) as policy_rpc:
        class Tools:
            descriptions = {}

            async def call(self, name, arguments):
                request = policy_rpc if name in {"search_policy", "read_policy"} else business_rpc
                response = request("tools/call", {"name": name, "arguments": arguments})
                return validate_output(name, response["structuredContent"], is_error=response.get("isError", False))

        async def run_graph():
            graph = build_graph(Tools(), InMemorySaver())
            config = {"configurable": {"thread_id": PROBLEM}}
            initial = {"job": {"problem_id": PROBLEM, "requester_id": EMPLOYEE, "platform": "GITHUB", "contents": "payment-core push가 안 돼요"}, "events": []}
            state = await graph.ainvoke(initial, config)
            assert state["result"]["status"] == "WAITING_APPROVAL"
            assert held["role"] is None and not any(path.endswith("/grant") for path, _ in calls)
            state = await graph.ainvoke(Command(resume={"approved": True,
                "plan_hash": Plan.model_validate(state["plan"]).digest(), "idempotency_key": "approved-key"}), config)
            assert state["result"]["status"] == "DONE" and state["result"]["verification_ok"] is True
            assert calls[-2:] == [(f"/internal/problems/{PROBLEM}/grant", {"idempotencyKey": "approved-key"}),
                ("/internal/access-verifications", {"employeeId": EMPLOYEE, "resourceId": RESOURCE, "requestedRole": "Write"})]

        asyncio.run(run_graph())
