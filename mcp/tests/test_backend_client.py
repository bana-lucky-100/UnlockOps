"""Shared Spring HTTP transport: authentication, typed failures and no redirects."""
import httpx
import pytest
from unlockops.common.models import ToolFailure
from unlockops_mcp.backend_client import BackendClient
PROBLEM = "40000000-0000-0000-0000-000000000001"

def bridge(handler):
    return BackendClient(httpx.Client(transport=httpx.MockTransport(handler)), base_url="http://backend:8080", token="internal-secret")

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
        client._post("/internal/v2/problems/" + PROBLEM + "/execute", {})
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
        bridge(handler)._post("/internal/v2/problems/" + PROBLEM + "/execute", {})
    assert caught.value.code == code and caught.value.retryable is True
    assert len(calls) == 1
    assert "private" not in str(caught.value)


def test_redirect_cannot_forward_the_service_token_and_empty_token_makes_no_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://other.example/private"})

    client = bridge(handler)
    with pytest.raises(ToolFailure): client._request("GET", "/internal/v2/problems/" + PROBLEM + "/context")
    assert len(calls) == 1
    client.token = ""
    with pytest.raises(ToolFailure) as caught: client._request("GET", "/internal/v2/problems/" + PROBLEM + "/context")
    assert caught.value.code == "BACKEND_AUTH_FAILED" and len(calls) == 1
