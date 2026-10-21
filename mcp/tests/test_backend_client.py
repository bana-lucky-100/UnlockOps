"""Spring 내부 API를 대체해 MCP 어댑터의 실제 HTTP 입력·응답·오류 변환을 검증한다."""

from copy import deepcopy
import json

import httpx
import pytest

from unlockops.models import ToolFailure
from unlockops_mcp.backend_client import BackendClient

EMPLOYEE = "10000000-0000-0000-0000-000000000001"
RESOURCE = "20000000-0000-0000-0000-000000000001"
PROBLEM = "40000000-0000-0000-0000-000000000001"
PROFILE = {"id": EMPLOYEE, "employee_no": "E-001", "name": "김개발", "department_id": "dev",
           "department_name": "개발팀", "job_grade": "사원", "job_family": "DEV", "head_id": "head"}
CONTEXT = {"profile": PROFILE, "resource_id": RESOURCE, "membership": {"tf_id": "tf", "member": True, "leader_id": "leader"},
           "current": {"role": None, "source": "github-team-membership", "teams": []}, "maximum_role": "Write",
           "budget": None, "rule_source": "A-ACCESS-03", "source_hashes": {"company-a-access-matrix.md": "a" * 64}}


def bridge(handler):
    return BackendClient(httpx.Client(transport=httpx.MockTransport(handler)), base_url="http://backend:8080", token="internal-secret")


@pytest.mark.parametrize("method,args,path,body,response,expected", [
    ("profile", (EMPLOYEE,), "/internal/access-context", {"employeeId": EMPLOYEE}, {"profile": PROFILE}, PROFILE),
    ("membership", (EMPLOYEE, RESOURCE), "/internal/access-context", {"employeeId": EMPLOYEE, "resourceId": RESOURCE}, CONTEXT, CONTEXT["membership"]),
    ("current", (EMPLOYEE, RESOURCE), "/internal/access-context", {"employeeId": EMPLOYEE, "resourceId": RESOURCE}, CONTEXT, CONTEXT["current"]),
    ("budget", (EMPLOYEE,), "/internal/access-context", {"employeeId": EMPLOYEE, "includeBudget": True}, {"profile": PROFILE, "budget": None}, None),
    ("resolve", ("GITHUB", "payment-core"), "/internal/resources/resolve", {"platform": "GITHUB", "hint": "payment-core"}, {"matches": [], "ambiguous": True}, {"matches": [], "ambiguous": True}),
    ("access_rules", (EMPLOYEE, RESOURCE), "/internal/access-context", {"employeeId": EMPLOYEE, "resourceId": RESOURCE}, CONTEXT, CONTEXT),
    ("grant", (PROBLEM, "approved-key"), f"/internal/problems/{PROBLEM}/grant", {"idempotencyKey": "approved-key"}, {"ok": True, "changed": True, "role": "Write"}, {"ok": True, "changed": True, "role": "Write"}),
    ("verify", (EMPLOYEE, RESOURCE, "Write"), "/internal/access-verifications", {"employeeId": EMPLOYEE, "resourceId": RESOURCE, "requestedRole": "Write"}, {"ok": True, "verified": False, "current": {"role": None}}, {"ok": True, "verified": False, "current": {"role": None}}),
])
def test_tools_use_matching_spring_dto_and_service_auth(method, args, path, body, response, expected):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.path == path
        assert request.headers["Authorization"] == "Bearer internal-secret"
        assert json.loads(request.content) == body
        return httpx.Response(200, json=response)

    assert getattr(bridge(handler), method)(*args) == expected
    assert len(calls) == 1


@pytest.mark.parametrize("status,payload,code,retryable,reason", [
    (401, {"message": "private token"}, "BACKEND_AUTH_FAILED", False, None),
    (403, {}, "BACKEND_AUTH_FAILED", False, None),
    (400, {"message": "invalid"}, "INVALID_TOOL_INPUT", False, None),
    (404, {"message": "private"}, "NOT_FOUND", False, None),
    (409, {"message": "private"}, "BACKEND_CONFLICT", False, None),
    (503, {"message": "private SQL"}, "UPSTREAM_UNAVAILABLE", True, None),
    (500, {"message": "private SQL"}, "UPSTREAM_UNAVAILABLE", True, None),
    (429, {}, "UPSTREAM_UNAVAILABLE", True, None),
    (503, {"message": "private path", "code": "POLICY_SOURCE_UNAVAILABLE", "retryable": False}, "POLICY_SOURCE_UNAVAILABLE", False, None),
    (409, {"ok": False, "error": {"code": "PRECONDITION_CHANGED", "message": "private reason", "retryable": False, "reason": "BUDGET_INSUFFICIENT"}}, "PRECONDITION_CHANGED", False, "BUDGET_INSUFFICIENT"),
    (409, {"ok": False, "error": {"code": "APPROVAL_REQUIRED", "message": "private", "retryable": False}}, "APPROVAL_REQUIRED", False, None),
    (503, {"ok": False, "error": {"code": "MOCK_JIRA_UNAVAILABLE", "message": "private", "retryable": True}}, "MOCK_JIRA_UNAVAILABLE", True, None),
    (503, {"ok": False, "error": {"code": "BROKEN", "message": "private", "retryable": "false"}}, "INVALID_TOOL_OUTPUT", False, None),
])
def test_http_errors_preserve_codes_and_hide_provider_details(status, payload, code, retryable, reason):
    client = bridge(lambda request: httpx.Response(status, json=payload))
    with pytest.raises(ToolFailure) as caught:
        client.grant(PROBLEM, "key")
    assert (caught.value.code, caught.value.retryable, caught.value.reason) == (code, retryable, reason)
    assert "private" not in str(caught.value) and "internal-secret" not in str(caught.value)


@pytest.mark.parametrize("error,code", [(httpx.ConnectError("private URL"), "UPSTREAM_UNAVAILABLE"),
                                      (httpx.ReadTimeout("private token"), "UPSTREAM_TIMEOUT")])
def test_transport_failure_does_not_retry_or_fall_back_to_database(error, code):
    calls = []

    def handler(request):
        calls.append(request)
        raise error

    with pytest.raises(ToolFailure) as caught:
        bridge(handler).grant(PROBLEM, "same-key")
    assert caught.value.code == code and caught.value.retryable is True
    assert len(calls) == 1
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("patch,code", [
    ({"profile": {**PROFILE, "id": "another-employee"}}, "EMPLOYEE_SCOPE"),
    ({"resource_id": "20000000-0000-0000-0000-000000000002"}, "RESOURCE_SCOPE"),
    ({"membership": None}, "INVALID_TOOL_OUTPUT"), ({"current": {"role": None, "can_browse": "false"}}, "INVALID_TOOL_OUTPUT"),
    ({"maximum_role": None}, "INVALID_TOOL_OUTPUT"), ({"budget": {"remaining_monthly_amount": "10", "unit_monthly_price": "0"}}, "INVALID_TOOL_OUTPUT"),
])
def test_context_rejects_wrong_identity_missing_facts_and_invalid_types(patch, code):
    with pytest.raises(ToolFailure) as caught:
        bridge(lambda request: httpx.Response(200, json={**deepcopy(CONTEXT), **patch})).access_rules(EMPLOYEE, RESOURCE)
    assert caught.value.code == code


@pytest.mark.parametrize("payload", [{}, {"ok": True, "verified": "false", "current": {"role": None}},
    {"ok": True, "verified": True}, {"ok": False, "error": {}}, []])
def test_verification_never_accepts_missing_or_ambiguous_success(payload):
    with pytest.raises(ToolFailure) as caught:
        bridge(lambda request: httpx.Response(200, json=payload)).verify(EMPLOYEE, RESOURCE, "Write")
    assert caught.value.code == "INVALID_TOOL_OUTPUT"


def test_grant_and_verification_are_not_cached_and_verification_sees_revocation():
    writes, reads = [], []
    permissions = ["Write", None]

    def handler(request):
        if request.url.path.endswith("/grant"):
            writes.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "changed": True, "role": "Write"})
        reads.append(request)
        role = permissions.pop(0)
        return httpx.Response(200, json={"ok": True, "verified": role == "Write", "current": {"role": role}})

    client = bridge(handler)
    assert client.grant(PROBLEM, "same-key") == client.grant(PROBLEM, "same-key")
    assert writes == [{"idempotencyKey": "same-key"}] * 2
    assert client.verify(EMPLOYEE, RESOURCE, "Write")["verified"] is True
    assert client.verify(EMPLOYEE, RESOURCE, "Write")["verified"] is False
    assert len(reads) == 2


def test_redirect_cannot_forward_the_service_token_and_empty_token_makes_no_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://other.example/private"})

    client = bridge(handler)
    with pytest.raises(ToolFailure): client.profile(EMPLOYEE)
    assert len(calls) == 1
    client.token = ""
    with pytest.raises(ToolFailure) as caught: client.profile(EMPLOYEE)
    assert caught.value.code == "BACKEND_AUTH_FAILED" and len(calls) == 1


def test_missing_budget_field_is_not_silently_treated_as_no_budget():
    with pytest.raises(ToolFailure) as caught:
        bridge(lambda request: httpx.Response(200, json={"profile": PROFILE})).budget(EMPLOYEE)
    assert caught.value.code == "INVALID_TOOL_OUTPUT"


def test_access_search_uses_spring_ceiling_and_checks_source_version(monkeypatch):
    from unlockops.rules import source_hashes
    from unlockops_mcp import business

    context = {**deepcopy(CONTEXT), "maximum_role": "Read", "source_hashes": source_hashes()}
    monkeypatch.setattr(business, "repo", bridge(lambda request: httpx.Response(200, json=context)))
    assert business.search_access_rules("query", EMPLOYEE, RESOURCE)["maximum_role"] == "Read"
    context["source_hashes"] = {"company-a-access-matrix.md": "old"}
    with pytest.raises(ToolFailure) as caught: business.search_access_rules("query", EMPLOYEE, RESOURCE)
    assert caught.value.code == "POLICY_SOURCE_UNAVAILABLE"
