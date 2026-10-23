"""MCP 연결·호출과 진단 단계의 읽기 범위·횟수 제한을 담당한다."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from copy import deepcopy
import json

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError

from .contracts import validate_input, validate_output
from .models import ToolFailure
from .settings import settings

# LLM 조사 중에는 이 목록의 읽기 도구만 사용할 수 있다.
READ_TOOLS = {
    "get_employee_profile",
    "resolve_resource",
    "get_tf_membership",
    "get_current_permissions",
    "check_budget",
    "search_access_rules",
    "read_access_rule",
    "search_policy",
    "read_policy",
}


class MCPTools:
    """두 MCP 서버를 연결하고 도구 이름에 맞는 서버로 호출을 보낸다."""

    def __init__(self):
        """MCP 연결 수명과 도구별 세션·설명 저장소를 준비한다."""
        self.stack = AsyncExitStack()
        self.sessions = {}
        self.descriptions = {}

    async def __aenter__(self):
        # async with 진입 시 연결하고, 도구 목록·입력 스키마를 받아 둔다.
        """두 MCP 서버에 연결해 세션을 초기화하고 도구 목록을 수집한다."""
        try:
            for url in (settings.policy_url, settings.business_url):
                read, write, _ = await self.stack.enter_async_context(
                    streamablehttp_client(
                        url, headers={"Authorization": "Bearer " + settings.mcp_token}
                    )
                )
                session = await self.stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                response = await session.list_tools()
                for tool in response.tools:
                    if tool.name in self.sessions:
                        raise RuntimeError("Duplicate MCP tool name")
                    self.sessions[tool.name] = session
                    self.descriptions[tool.name] = {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema,
                        },
                    }
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args):
        """관리 중인 MCP 세션과 HTTP 연결을 닫는다."""
        await self.stack.aclose()

    async def call(self, name, arguments):
        """입력 검사 → 시간 제한을 둔 원격 호출 → 응답 검사 순서로 실행한다."""
        if name not in self.sessions:
            raise ToolFailure("UNKNOWN_TOOL", "Tool is not in the two connected MCP servers")
        arguments = validate_input(name, arguments)
        try:
            response = await asyncio.wait_for(
                self.sessions[name].call_tool(name, arguments), timeout=settings.tool_timeout
            )
        except TimeoutError:
            raise ToolFailure("TOOL_TIMEOUT", "MCP tool timed out", True) from None
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code in {408, 429, 502, 503, 504}
            code = "MCP_AUTH_FAILED" if exc.response.status_code in {401, 403} else "MCP_HTTP_ERROR"
            raise ToolFailure(code, "MCP HTTP request failed", retryable) from None
        except (
            httpx.TransportError,
            OSError,
            anyio.EndOfStream,
            anyio.BrokenResourceError,
            anyio.ClosedResourceError,
        ):
            raise ToolFailure("MCP_UNAVAILABLE", "MCP transport failed", True) from None
        except McpError as exc:
            code = {-32601: "UNKNOWN_TOOL", -32602: "INVALID_TOOL_INPUT"}.get(
                exc.error.code, "MCP_PROTOCOL_ERROR"
            )
            raise ToolFailure(code, "MCP protocol request failed") from None
        except RuntimeError:
            # SDK가 공개된 outputSchema 검사에서 실패한 경우도 응답 오류로 분류한다.
            raise ToolFailure("INVALID_TOOL_OUTPUT", "MCP result failed SDK validation") from None
        except Exception:
            raise ToolFailure("MCP_CLIENT_ERROR", "MCP client request failed") from None
        if response.structuredContent is not None:
            data = response.structuredContent
        else:
            texts = [c.text for c in response.content if getattr(c, "type", "") == "text"]
            try:
                data = json.loads("".join(texts))
            except ValueError:
                code = "TOOL_ERROR" if response.isError else "INVALID_TOOL_OUTPUT"
                raise ToolFailure(code, "MCP output is not structured JSON") from None
        return validate_output(name, data, is_error=response.isError)


class ScopedTools:
    """한 분석 안에서 요청자·플랫폼·자원을 고정하고 읽기 호출 예산을 관리한다."""

    def __init__(self, tools, requester_id, platform, resource_id=None, *, access_scope=None):
        """한 분석의 요청자·플랫폼·자원 범위와 호출 횟수·캐시를 초기화한다."""
        self.tools, self.requester_id, self.platform = tools, requester_id, platform
        self.resource_id = resource_id
        self.access_scope = access_scope
        self.calls = 0
        self.optional_calls = 0
        self.trace = []
        self.optional_evidence = []
        # 이 분석 노드에서만 재사용한다. 승인 후 실행·검증에는 넘기지 않는다.
        self.cache = {}

    async def read(self, name, arguments, *, optional=False):
        """선택 조회 횟수를 제한하고 실패 코드를 추적하며 읽기 도구를 호출한다."""
        if optional:
            if self.optional_calls >= settings.max_optional_tools:
                raise ToolFailure("OPTIONAL_TOOL_BUDGET", "Optional tool selection limit reached")
            # 잘못된 범위 요청·캐시 적중도 모델의 선택 횟수에는 포함한다.
            self.optional_calls += 1
        try:
            value = await self._read(name, arguments, optional=optional)
            if optional and name in {"search_policy", "read_policy"}:
                self.optional_evidence.extend(value.get("hits", value.get("chunks", [])))
            return value
        except ToolFailure as exc:
            self.trace.append({"tool": name, "ok": False, "code": exc.code, "optional": optional})
            raise

    async def _read(self, name, arguments, *, optional):
        """읽기 범위·총 호출 한도를 검사하고 응답 검증 및 분석 내 캐시를 처리한다."""
        if name not in READ_TOOLS:
            raise ToolFailure(
                "WRITE_DURING_DIAGNOSIS", "Only read tools are exposed during diagnosis"
            )
        if "employee_id" in arguments and arguments["employee_id"] != self.requester_id:
            raise ToolFailure("EMPLOYEE_SCOPE", "Cannot inspect another employee")
        if "platform" in arguments and arguments["platform"] != self.platform:
            raise ToolFailure("PLATFORM_SCOPE", "Cannot switch request platform")
        if (
            self.resource_id
            and "resource_id" in arguments
            and arguments["resource_id"] != self.resource_id
        ):
            raise ToolFailure("RESOURCE_SCOPE", "Cannot switch request resource")
        key = (name, json.dumps(arguments, sort_keys=True))
        if optional and key in self.cache:
            self.trace.append({"tool": name, "ok": True, "optional": True, "cached": True})
            return deepcopy(self.cache[key])
        if self.calls >= settings.max_tools:
            raise ToolFailure("TOOL_BUDGET", "Tool call limit reached")
        self.calls += 1
        value = validate_output(name, await self.tools.call(name, arguments))
        if name == "search_access_rules":
            context = value["context"]
            if context["profile"]["id"] != self.requester_id:
                raise ToolFailure("EMPLOYEE_SCOPE", "Cannot use another employee's context")
            if context["resource_id"] != arguments["resource_id"]:
                raise ToolFailure("RESOURCE_SCOPE", "Cannot use another resource's context")
            # 같은 분석의 선택 조회도 이 스냅샷을 사용한다. 전역·승인 후 캐시는 만들지 않는다.
            projections = [
                ("get_employee_profile", {"employee_id": self.requester_id}, context["profile"]),
                ("get_tf_membership", {k: arguments[k] for k in ("employee_id", "resource_id")}, context["membership"]),
                ("get_current_permissions", {k: arguments[k] for k in ("employee_id", "resource_id")}, context["current"]),
            ]
            if context["budget"] is not None or self.access_scope == "SEAT":
                projections.append(("check_budget", {"employee_id": self.requester_id}, {"budget": context["budget"]}))
            for tool, args, result in projections:
                self.cache[(tool, json.dumps(args, sort_keys=True))] = deepcopy(result)
        self.cache[key] = deepcopy(value)
        self.trace.append({"tool": name, "ok": True, "optional": optional})
        return value
