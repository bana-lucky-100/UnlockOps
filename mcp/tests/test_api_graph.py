"""실제 Graph → MCP HTTP → Spring HTTP 어댑터 계약을 연결한다. Spring 응답만 대체한다."""

from copy import deepcopy
import asyncio
import json

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from unlockops.common.contracts import validate_output
from unlockops.access.graph import build_graph
from unlockops.common.models import Plan
from unlockops.access.rules import source_hashes
from unlockops_mcp import business
from unlockops_mcp.backend_client import BackendClient
from unlockops_mcp.policy import mcp as policy_mcp
from test_http import rpc
from test_backend_client import CONTEXT, EMPLOYEE, PROFILE, RESOURCE, PROBLEM


@pytest.mark.parametrize("seat", [False, True])
def test_api_backed_tools_wait_for_approval_then_execute_and_verify(monkeypatch, seat):
    calls, held = [], {"role": None}
    role = "Seat" if seat else "Write"
    resource = {"id": RESOURCE, "external_id": "copilot-seat" if seat else "payment-core",
                "name": "Copilot" if seat else "payment-core", "platform": "GITHUB", "access_scope": "SEAT" if seat else "TF"}

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        if request.url.path == "/internal/resources/resolve":
            return httpx.Response(200, json={"matches": [resource], "ambiguous": False})
        if request.url.path == "/internal/access-context":
            context = {**deepcopy(CONTEXT), "source_hashes": source_hashes(), "profile": PROFILE,
                "current": {"role": held["role"]}, "membership": {"member": True, "leader_id": "leader"},
                "maximum_role": role, "budget": {"remaining_monthly_amount": "150.00", "unit_monthly_price": "19.00"} if seat else None}
            if "resourceId" not in json.loads(request.content):
                context["profile"] = {**PROFILE, "department_name": "이전 부서"}
            return httpx.Response(200, json=context)
        if request.url.path.endswith("/grant"):
            assert json.loads(request.content) == {"idempotencyKey": "approved-key"}
            held["role"] = role
            return httpx.Response(200, json={"ok": True, "changed": True, "role": role})
        if request.url.path == "/internal/access-verifications":
            return httpx.Response(200, json={"ok": True, "verified": held["role"] == role, "current": {"role": held["role"]}})
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
            initial = {"job": {"problem_id": PROBLEM, "requester_id": EMPLOYEE, "platform": "GITHUB",
                               "contents": "Copilot 좌석 신청합니다" if seat else "payment-core push가 안 돼요"}, "events": []}
            state = await graph.ainvoke(initial, config)
            assert state["result"]["status"] == "WAITING_APPROVAL"
            assert held["role"] is None and not any(path.endswith("/grant") for path, _ in calls)
            contexts = [body for path, body in calls if path == "/internal/access-context"]
            assert contexts == [{"employeeId": EMPLOYEE}, {"employeeId": EMPLOYEE, "resourceId": RESOURCE}]
            assert state["profile"] == PROFILE
            assert state["membership"] == {"member": True, "leader_id": "leader"}
            assert state["current"] == {"role": None}
            assert state["budget"] == ({"remaining_monthly_amount": "150.00", "unit_monthly_price": "19.00"} if seat else None)
            state = await graph.ainvoke(Command(resume={"approved": True,
                "plan_hash": Plan.model_validate(state["plan"]).digest(), "idempotency_key": "approved-key"}), config)
            assert state["result"]["status"] == "DONE" and state["result"]["verification_ok"] is True
            assert calls[-2:] == [(f"/internal/problems/{PROBLEM}/grant", {"idempotencyKey": "approved-key"}),
                ("/internal/access-verifications", {"employeeId": EMPLOYEE, "resourceId": RESOURCE, "requestedRole": role})]

            # 같은 직원·자원이라도 다음 분석은 새 묶음을 읽고 변경된 권한을 본다.
            state = await graph.ainvoke(initial, {"configurable": {"thread_id": "next-analysis"}})
            assert state["current"]["role"] == role
            judge = next(event for event in state["events"] if event["node"] == "judge")
            assert judge["reason_code"] == ("DUPLICATE_SEAT" if seat else "ALREADY_HAS_ACCESS")
            assert sum(path == "/internal/access-context" and "resourceId" in body for path, body in calls) == 2

        asyncio.run(run_graph())
