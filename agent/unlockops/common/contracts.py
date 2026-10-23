"""One tool registry shared by the agent and both MCP servers."""
from typing import Annotated, Literal
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError
from .models import ToolFailure
from .tool_contracts import INPUTS, OUTPUTS

def boolean_only(value):
    if type(value) is not bool:
        raise ValueError("A JSON boolean is required")
    return value

FalseFlag = Annotated[Literal[False], BeforeValidator(boolean_only)]

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorDetail(Input):
    code: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")]
    message: Annotated[str, Field(min_length=1, max_length=500)]
    retryable: bool
    reason: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")] | None = None


class ErrorResult(Input):
    ok: FalseFlag
    error: ErrorDetail



def validate_input(name: str, arguments: dict) -> dict:
    """호출 전에 도구별 인자를 검사하고 JSON으로 보낼 값으로 바꾼다."""
    if name not in INPUTS:
        raise ToolFailure("UNKNOWN_TOOL", "Tool has no registered contract")
    try:
        return INPUTS[name].model_validate(arguments).model_dump(mode="json")
    except ValidationError:
        raise ToolFailure(
            "INVALID_TOOL_INPUT", "MCP arguments do not match the tool contract"
        ) from None


def validate_output(name: str, data: object, *, is_error: bool = False) -> dict:
    """성공 응답은 검사해 돌려주고, 오류 응답은 ToolFailure로 변환한다."""
    if name not in OUTPUTS:
        raise ToolFailure("UNKNOWN_TOOL", "Tool has no registered contract")
    if not isinstance(data, dict):
        raise ToolFailure("INVALID_TOOL_OUTPUT", "MCP output must be an object")
    try:
        if data.get("ok") is False:
            if "error" in data:
                error = ErrorResult.model_validate(data).error
                raise ToolFailure(error.code, error.message, error.retryable, error.reason)
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Tool error must contain a typed error object")
        if is_error:
            raise ToolFailure("INVALID_TOOL_OUTPUT", "MCP error has no valid error object")
        if "error" in data or "error_code" in data:
            raise ToolFailure(
                "INVALID_TOOL_OUTPUT", "MCP success contains contradictory error fields"
            )
        OUTPUTS[name].model_validate(data)
    except ValidationError:
        raise ToolFailure(
            "INVALID_TOOL_OUTPUT", "MCP response does not match the tool contract"
        ) from None
    # 검사 과정에서 생성된 기본값을 덧붙이지 않고 원래 응답과 출처를 보존한다.
    return data


def error_payload(error: ToolFailure) -> dict:
    """서버 예외를 MCP 오류 응답의 공통 JSON 형식으로 만든다."""
    return ErrorResult(
        ok=False,
        error=ErrorDetail(
            code=error.code,
            message=str(error),
            retryable=error.retryable,
            reason=error.reason,
        ),
    ).model_dump(mode="json", exclude_none=True)
