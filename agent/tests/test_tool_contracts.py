"""Client boundary checks without starting a server or contacting a provider."""
import json

import httpx
from mcp.shared.exceptions import McpError
from mcp.types import CallToolResult, ErrorData, TextContent
import pytest

from unlockops.models import ToolFailure
from unlockops.tools import MCPTools


IDS = {"employee_id": "10000000-0000-0000-0000-000000000001",
       "resource_id": "20000000-0000-0000-0000-000000000001", "requested_role": "Write"}


class Session:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if isinstance(self.result, Exception): raise self.result
        return self.result


def client(result):
    tools = MCPTools()
    session = Session(result)
    tools.sessions["verify_permission"] = session
    return tools, session


@pytest.mark.parametrize("structured", [True, False])
async def test_valid_verification_preserves_false_and_json_text_fallback(structured):
    data = {"verified": False}
    tools, _ = client(CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        structuredContent=data if structured else None,
    ))
    assert await tools.call("verify_permission", IDS) == data


@pytest.mark.parametrize("data", [
    {}, {"verified": "false"}, {"verified": 1}, {"verified": None},
    {"verified": True, "ok": 1}, [],
])
async def test_invalid_verification_is_not_success_or_retryable(data):
    response = CallToolResult(content=[TextContent(type="text", text=json.dumps(data))])
    tools, _ = client(response)
    with pytest.raises(ToolFailure) as caught:
        await tools.call("verify_permission", IDS)
    assert caught.value.code == "INVALID_TOOL_OUTPUT"
    assert caught.value.retryable is False


@pytest.mark.parametrize("data,is_error,code,retryable", [
    ({"ok": False, "error": {"code": "UPSTREAM_UNAVAILABLE", "message": "Try later", "retryable": True}}, True, "UPSTREAM_UNAVAILABLE", True),
    ({"ok": False, "error": {"code": "APPROVAL_REQUIRED", "message": "Approval required", "retryable": False}}, True, "APPROVAL_REQUIRED", False),
    ({"ok": False, "error_code": "MOCK_JIRA_UNAVAILABLE", "retryable": True}, False, "MOCK_JIRA_UNAVAILABLE", True),
    ({"ok": False, "error_code": "BROKEN", "retryable": "false"}, False, "INVALID_TOOL_OUTPUT", False),
    ({"verified": True}, True, "INVALID_TOOL_OUTPUT", False),
])
async def test_structured_and_legacy_errors_retain_retryability(data, is_error, code, retryable):
    tools, _ = client(CallToolResult(content=[], structuredContent=data, isError=is_error))
    with pytest.raises(ToolFailure) as caught:
        await tools.call("verify_permission", IDS)
    assert (caught.value.code, caught.value.retryable) == (code, retryable)


@pytest.mark.parametrize("patch", [
    {"employee_id": "invalid-id"}, {"requested_role": "Admin"}, {"unexpected": True},
])
async def test_invalid_inputs_do_not_reach_transport(patch):
    tools, session = client(CallToolResult(content=[], structuredContent={"verified": True}))
    with pytest.raises(ToolFailure) as caught:
        await tools.call("verify_permission", {**IDS, **patch})
    assert caught.value.code == "INVALID_TOOL_INPUT"
    assert session.calls == []


@pytest.mark.parametrize("error,code,retryable", [
    (TimeoutError(), "TOOL_TIMEOUT", True),
    (httpx.ConnectError("private transport detail"), "MCP_UNAVAILABLE", True),
    (McpError(ErrorData(code=-32602, message="private input detail")), "INVALID_TOOL_INPUT", False),
    (RuntimeError("private SDK output detail"), "INVALID_TOOL_OUTPUT", False),
    (ValueError("private client detail"), "MCP_CLIENT_ERROR", False),
])
async def test_transport_protocol_and_contract_failures_are_distinct(error, code, retryable):
    tools, _ = client(error)
    with pytest.raises(ToolFailure) as caught:
        await tools.call("verify_permission", IDS)
    assert (caught.value.code, caught.value.retryable) == (code, retryable)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("status,retryable", [(401, False), (403, False), (400, False), (429, True), (503, True)])
async def test_http_authentication_errors_are_not_retried(status, retryable):
    response = httpx.Response(status, request=httpx.Request("POST", "http://mcp.test"))
    tools, _ = client(httpx.HTTPStatusError("private response body", request=response.request, response=response))
    with pytest.raises(ToolFailure) as caught:
        await tools.call("verify_permission", IDS)
    assert caught.value.retryable == retryable
    assert "private" not in str(caught.value)
