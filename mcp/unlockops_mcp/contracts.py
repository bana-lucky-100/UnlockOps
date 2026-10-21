"""Agent와 같은 스키마로 MCP 입출력을 검사하고 오류를 공통 형식으로 바꾼다."""

import json

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from unlockops.contracts import INPUTS, OUTPUTS, error_payload, validate_input, validate_output
from unlockops.models import ToolFailure


# @mcp.tool에서 도구 성격을 명시한다. 힌트이며 실제 승인·범위 검사를 대신하지 않는다.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
APPROVED_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)


def classify_error(exc: Exception) -> ToolFailure:
    """SDK가 감싼 예외의 원인을 확인하되 SQL·인증 정보 등 원문은 노출하지 않는다."""
    causes = []
    current = exc
    while current is not None and current not in causes:
        causes.append(current)
        current = current.__cause__
    for cause in causes:
        if isinstance(cause, ToolFailure):
            return cause
        if isinstance(cause, ValidationError):
            return ToolFailure("INVALID_TOOL_OUTPUT", "Tool returned an invalid response")
        if isinstance(cause, httpx.TransportError):
            return ToolFailure(
                "UPSTREAM_UNAVAILABLE", "Upstream service is temporarily unavailable", True
            )
        if isinstance(cause, ValueError):
            return ToolFailure("NOT_FOUND", "Requested record or document was not found")
    return ToolFailure("INTERNAL_TOOL_ERROR", "Tool execution failed")


class ContractMCP(FastMCP):
    """일반 도구 함수는 업무만 담당하고, 공통 검사는 서버 경계에서 수행한다."""

    async def list_tools(self):
        """공개 도구 목록의 입출력 스키마를 Agent와 공유하는 계약으로 맞춘다."""
        definitions = await super().list_tools()
        for tool in definitions:
            tool.inputSchema = INPUTS[tool.name].model_json_schema()
            tool.outputSchema = OUTPUTS[tool.name].model_json_schema()
        return definitions

    async def call_tool(self, name, arguments):
        # 입력 검사 → 도구 실행 → 응답 검사 순서로 처리한다.
        """입력 검사·도구 실행·출력 검사를 수행하고 예외를 공통 MCP 오류로 반환한다."""
        try:
            if name not in {tool.name for tool in await super().list_tools()}:
                raise ToolFailure("UNKNOWN_TOOL", "Tool is not provided by this server")
            arguments = validate_input(name, arguments)
            result = await super().call_tool(name, arguments)
            # SDK 응답에서 JSON만 꺼낸다. 이 차이는 Agent 노드가 몰라도 된다.
            if isinstance(result, CallToolResult):
                data, is_error = result.structuredContent, result.isError
            elif isinstance(result, tuple) and len(result) == 2:
                data, is_error = result[1], False
            else:
                data, is_error = result, False
            data = validate_output(name, data, is_error=is_error)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
                structuredContent=data,
                isError=False,
            )
        except Exception as exc:
            data = error_payload(classify_error(exc))
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
                structuredContent=data,
                isError=True,
            )
