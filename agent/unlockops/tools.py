from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .models import ToolFailure
from .settings import settings

READ_TOOLS = {
    "get_employee_profile", "resolve_resource", "get_tf_membership", "get_current_permissions",
    "check_budget", "search_access_rules", "read_access_rule", "search_policy", "read_policy",
}


class MCPTools:
    """Two real MCP clients, per-call timeouts and explicit read/write separation."""
    def __init__(self):
        self.stack = AsyncExitStack()
        self.sessions = {}
        self.descriptions = {}

    async def __aenter__(self):
        try:
            for url in (settings.policy_url, settings.business_url):
                read, write, _ = await self.stack.enter_async_context(streamablehttp_client(
                    url, headers={"Authorization": "Bearer " + settings.mcp_token}))
                session = await self.stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                response = await session.list_tools()
                for tool in response.tools:
                    if tool.name in self.sessions: raise RuntimeError("Duplicate MCP tool name")
                    self.sessions[tool.name] = session
                    self.descriptions[tool.name] = {"type": "function", "function": {
                        "name": tool.name, "description": tool.description or "",
                        "parameters": tool.inputSchema}}
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args):
        await self.stack.aclose()

    async def call(self, name, arguments):
        if name not in self.sessions:
            raise ToolFailure("UNKNOWN_TOOL", "Tool is not in the two connected MCP servers")
        try:
            response = await asyncio.wait_for(self.sessions[name].call_tool(name, arguments),
                                               timeout=settings.tool_timeout)
        except TimeoutError:
            raise ToolFailure("TOOL_TIMEOUT", "MCP tool timed out", True) from None
        except Exception:
            raise ToolFailure("MCP_UNAVAILABLE", "MCP transport failed", True) from None
        if response.isError:
            raise ToolFailure("TOOL_ERROR", "MCP rejected tool arguments or execution")
        if response.structuredContent is not None:
            data = response.structuredContent
        else:
            texts = [c.text for c in response.content if getattr(c, "type", "") == "text"]
            try: data = json.loads("".join(texts))
            except ValueError: raise ToolFailure("INVALID_TOOL_OUTPUT", "MCP output is not structured JSON") from None
        if not isinstance(data, dict): raise ToolFailure("INVALID_TOOL_OUTPUT", "MCP output must be an object")
        if data.get("ok") is False:
            raise ToolFailure(data.get("error_code", "BUSINESS_ERROR"), "Business operation was not applied", data.get("retryable", False))
        return data


class ScopedTools:
    def __init__(self, tools, requester_id, platform, resource_id=None):
        self.tools, self.requester_id, self.platform = tools, requester_id, platform
        self.resource_id = resource_id
        self.calls = 0
        self.trace = []

    async def read(self, name, arguments):
        if name not in READ_TOOLS: raise ToolFailure("WRITE_DURING_DIAGNOSIS", "Only read tools are exposed during diagnosis")
        if "employee_id" in arguments and arguments["employee_id"] != self.requester_id:
            raise ToolFailure("EMPLOYEE_SCOPE", "Cannot inspect another employee")
        if "platform" in arguments and arguments["platform"] != self.platform:
            raise ToolFailure("PLATFORM_SCOPE", "Cannot switch request platform")
        if self.resource_id and "resource_id" in arguments and arguments["resource_id"] != self.resource_id:
            raise ToolFailure("RESOURCE_SCOPE", "Cannot switch request resource")
        self.calls += 1
        if self.calls > settings.max_tools: raise ToolFailure("TOOL_BUDGET", "Tool call limit reached")
        value = await self.tools.call(name, arguments)
        self.trace.append({"tool": name, "ok": True})
        return value
