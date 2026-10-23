"""Shared request interpretation and typed tool failures."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Intent(BaseModel):
    """사용자 문장 해석 결과. 직원의 실제 자격은 별도 MCP 조회로 확인한다."""

    model_config = ConfigDict(extra="forbid")
    request_type: Literal["GUIDE", "TROUBLESHOOT", "ACCESS_REQUEST"] = Field(
        default="TROUBLESHOOT",
        description="사용법 문의 / 오류 해결 / 권한 신청. 실제 권한 부족 여부나 부여 자격은 별도 조회로 판단한다.",
    )
    resource_hint: str = Field(default="", max_length=200)
    requested_role: str = Field(default="", max_length=100)
    symptom: str = Field(default="", max_length=500)
    out_of_scope: bool = False


class ToolFailure(RuntimeError):
    """도구 실패의 코드와 재시도 가능 여부를 노드까지 전달한다."""

    def __init__(self, code: str, message: str, retryable: bool = False, reason: str | None = None):
        """도구 실패의 공통 코드·메시지와 재시도 가능 여부를 저장한다."""
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.reason = reason
