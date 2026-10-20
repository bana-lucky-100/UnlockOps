"""MCP HTTP lifespan/authentication checks; no DB or external model calls."""

import asyncio
import pytest
from contextlib import contextmanager
import jsonschema
import psycopg
from starlette.testclient import TestClient

from unlockops.settings import settings
from unlockops_mcp.auth import TokenAuth
from unlockops_mcp.business import mcp as business_mcp
from unlockops_mcp.policy import mcp as policy_mcp
from unlockops.contracts import validate_output
from unlockops.contracts import INPUTS
from unlockops.models import ToolFailure
from unlockops_mcp.contracts import ContractMCP


EMPLOYEE = "10000000-0000-0000-0000-000000000001"
RESOURCE = "20000000-0000-0000-0000-000000000001"


@contextmanager
def rpc(server):
    """실제 도구를 새 테스트 서버에 등록하고 인증된 JSON-RPC 호출 함수를 제공한다."""
    from unlockops_mcp import business, policy

    # The SDK session manager has a single lifespan. Use a fresh server per test
    # while exercising the real registered tool functions and shared boundary.
    module = policy if server is policy_mcp else business
    names = {"search_policy", "read_policy"}
    if module is business:
        names = set(INPUTS) - names
    fresh = ContractMCP("unlockops-test", host="127.0.0.1", stateless_http=True, json_response=True)
    # 실제 @mcp.tool 데코레이터에 선언한 설명·힌트를 새 서버에도 복사한다.
    definitions = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name in sorted(names):
        fresh.add_tool(getattr(module, name), annotations=definitions[name].annotations)
    server = fresh
    with TestClient(
        TokenAuth(server.streamable_http_app()), base_url="http://127.0.0.1:8000"
    ) as client:
        headers = {
            "Authorization": "Bearer " + settings.mcp_token,
            "Accept": "application/json, text/event-stream",
        }

        def request(method, params):
            """인증 헤더를 포함한 MCP 요청을 보내고 JSON-RPC 결과를 반환한다."""
            response = client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params,
                },
            )
            assert response.status_code == 200
            return response.json()["result"]

        yield request


@pytest.mark.parametrize("server", [policy_mcp, business_mcp])
def test_server_starts_and_requires_token_for_discovery(server):
    """서버 기동과 토큰 인증 뒤 초기화·도구 목록 조회가 가능한지 확인한다."""
    with TestClient(
        TokenAuth(server.streamable_http_app()), base_url="http://127.0.0.1:8000"
    ) as client:
        assert client.get("/health").status_code == 401
        headers = {"Authorization": "Bearer " + settings.mcp_token}
        assert client.get("/health", headers=headers).json() == {"status": "UP"}
        assert client.post("/mcp", json={}).status_code == 401
        headers.update({"Accept": "application/json, text/event-stream"})
        response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "layout-test", "version": "1"},
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"].startswith("unlockops-")
        response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
        assert response.status_code == 200
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        expected = (
            {"search_policy", "read_policy"}
            if server is policy_mcp
            else {"get_employee_profile", "grant_permission", "verify_permission"}
        )
        assert names >= expected


@pytest.mark.parametrize(
    "server,name,args",
    [
        (business_mcp, "get_employee_profile", {"employee_id": "not-a-uuid"}),
        (business_mcp, "get_employee_profile", {"employee_id": EMPLOYEE, "extra": "ignored?"}),
        (business_mcp, "resolve_resource", {"platform": "OTHER", "hint": "payment-core"}),
        (
            business_mcp,
            "verify_permission",
            {"employee_id": EMPLOYEE, "resource_id": RESOURCE, "requested_role": "Admin"},
        ),
        (policy_mcp, "search_policy", {"query": "q", "platform": "GITHUB", "limit": 11}),
        (policy_mcp, "search_policy", {"query": "q", "platform": "GITHUB", "limit": "5"}),
        (policy_mcp, "read_policy", {"doc_id": "../../private"}),
    ],
)
def test_invalid_input_returns_structured_nonretryable_error(server, name, args):
    """입력 계약 위반을 공통 형식의 재시도 불가 오류로 반환하는지 확인한다."""
    with rpc(server) as request:
        result = request("tools/call", {"name": name, "arguments": args})
    assert result["isError"] is True
    error = result["structuredContent"]["error"]
    assert (error["code"], error["retryable"]) == ("INVALID_TOOL_INPUT", False)


def test_published_schemas_and_real_policy_output_match(monkeypatch):
    """공개한 출력 스키마와 실제 정책 응답·출처 메타데이터가 일치한다."""
    from unlockops_mcp.policy import index

    monkeypatch.setenv("EMBEDDING_BASE_URL", "")
    monkeypatch.setenv("EMBEDDING_MODEL", "")
    index.cache_clear()
    try:
        with rpc(policy_mcp) as request:
            tools = {tool["name"]: tool for tool in request("tools/list", {})["tools"]}
            result = request(
                "tools/call", {"name": "read_policy", "arguments": {"doc_id": "POL-03"}}
            )
        assert result["isError"] is False
        schema = tools["read_policy"]["outputSchema"]
        jsonschema.validate(result["structuredContent"], schema)
        assert tools["read_policy"]["annotations"]["readOnlyHint"] is True
        data = validate_output("read_policy", result["structuredContent"])
        assert data["chunks"][0]["source_hash"]
    finally:
        index.cache_clear()


@pytest.mark.parametrize(
    "payload,expected_code,retryable",
    [
        ({"ok": True, "verified": False, "current": {"role": None}}, None, None),
        ({"verified": "false"}, "INVALID_TOOL_OUTPUT", False),
        ({}, "INVALID_TOOL_OUTPUT", False),
        (
            psycopg.OperationalError("private SQL or connection detail"),
            "UPSTREAM_UNAVAILABLE",
            True,
        ),
        (ValueError("private lookup detail"), "NOT_FOUND", False),
        (RuntimeError("private implementation detail"), "INTERNAL_TOOL_ERROR", False),
    ],
)
def test_business_outputs_and_exceptions_follow_wire_contract(
    monkeypatch, payload, expected_code, retryable
):
    """업무 응답과 예외를 HTTP 경계에서 검증하고 내부 오류 원문을 숨긴다."""
    from unlockops_mcp.business import repo

    def verify(*args):
        """검증 도구에 지정한 업무 응답이나 예외를 주입한다."""
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr(repo, "verify", verify)
    with rpc(business_mcp) as request:
        result = request(
            "tools/call",
            {
                "name": "verify_permission",
                "arguments": {
                    "employee_id": EMPLOYEE,
                    "resource_id": RESOURCE,
                    "requested_role": "Write",
                },
            },
        )
    assert "private" not in str(result)
    if expected_code is None:
        assert result["isError"] is False
        assert (
            validate_output("verify_permission", result["structuredContent"])["verified"] is False
        )
    else:
        assert result["isError"] is True
        with pytest.raises(ToolFailure) as caught:
            validate_output("verify_permission", result["structuredContent"], is_error=True)
        assert (caught.value.code, caught.value.retryable) == (expected_code, retryable)


def test_legacy_grant_error_is_normalized_without_changing_repository(monkeypatch):
    """저장소의 이전 부여 오류를 MCP 경계에서 공통 오류 형식으로 변환한다."""
    from unlockops_mcp.business import repo

    monkeypatch.setattr(
        repo,
        "grant",
        lambda *args: {
            "ok": False,
            "error_code": "MOCK_JIRA_UNAVAILABLE",
            "retryable": True,
        },
    )
    with rpc(business_mcp) as request:
        result = request(
            "tools/call",
            {
                "name": "grant_permission",
                "arguments": {
                    "problem_id": "40000000-0000-0000-0000-000000000001",
                    "idempotency_key": "approved-key",
                },
            },
        )
        tools = {tool["name"]: tool for tool in request("tools/list", {})["tools"]}
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "MOCK_JIRA_UNAVAILABLE"
    assert result["structuredContent"]["error"]["retryable"] is True
    assert tools["grant_permission"]["annotations"]["readOnlyHint"] is False
    assert tools["grant_permission"]["annotations"]["idempotentHint"] is True


@pytest.mark.parametrize("server", [policy_mcp, business_mcp])
async def test_tool_decorators_publish_read_and_write_hints(server):
    """도구 목록에 읽기와 승인 후 쓰기 데코레이터의 힌트가 노출된다."""
    for tool in await server.list_tools():
        read_only = tool.name != "grant_permission"
        assert tool.annotations.readOnlyHint is read_only
        assert tool.annotations.destructiveHint is (not read_only)
        assert tool.annotations.idempotentHint is True
        assert tool.inputSchema
        assert tool.outputSchema
