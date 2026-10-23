"""MCP 연결·호출과 진단 단계의 읽기 범위·횟수 제한을 담당한다."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
import json

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError

from .contracts import validate_input, validate_output
from .models import ToolFailure
from .settings import settings

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
