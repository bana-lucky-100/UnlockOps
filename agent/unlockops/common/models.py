"""Shared request interpretation and typed tool failures."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class EntitlementSelection(BaseModel):
    """후보 확인 결과. ID가 null이면 맞는 후보가 없거나 하나로 정할 수 없다."""

    model_config = ConfigDict(extra="forbid")
    entitlement_id: UUID | None = Field(
        description="전달된 권한 후보 ID 하나. 해당 없음·불명확·안내만 필요한 경우는 null.",
    )


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
    entitlement_selection: EntitlementSelection | None = Field(
        default=None,
        description="후보를 받지 않은 기존 형식은 null. 후보를 확인했다면 선택 결과를 반환한다.",
    )


class ToolFailure(RuntimeError):
    """도구 실패의 코드와 재시도 가능 여부를 노드까지 전달한다."""

    def __init__(self, code: str, message: str, retryable: bool = False, reason: str | None = None):
        """도구 실패의 공통 코드·메시지와 재시도 가능 여부를 저장한다."""
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.reason = reason
