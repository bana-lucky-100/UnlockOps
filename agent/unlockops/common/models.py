"""Pydantic 데이터 모델: 입력·계획·결과의 형식을 검사한다. LLM 설정은 planner.py에 있다."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Platform(StrEnum):
    """요청 하나에서 선택할 수 있는 플랫폼."""

    GITHUB = "GITHUB"
    JIRA = "JIRA"
    SLACK = "SLACK"
    NOTION = "NOTION"


class Status(StrEnum):
    """백엔드·화면·DB와 함께 사용하는 처리 상태."""

    RECEIVED = "RECEIVED"
    DIAGNOSING = "DIAGNOSING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    DONE = "DONE"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"


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


class ResultType(StrEnum):
    """DONE의 완료 대상. 안내 제공은 실제 권한 반영을 의미하지 않는다."""

    GUIDANCE = "GUIDANCE"
    ACCESS_VERIFIED = "ACCESS_VERIFIED"


class Plan(BaseModel):
    """승인받을 요청자·자원·역할을 담은 불변 실행 계획의 형식."""

    model_config = ConfigDict(extra="forbid")
    problem_id: str
    requester_id: str
    platform: Platform
    resource_id: str
    resource_key: str
    requested_role: str

    def digest(self) -> str:
        # 키 순서와 공백을 고정해야 Python과 백엔드가 같은 계획 해시를 만든다.
        """승인 계획을 정렬된 JSON으로 직렬화해 비교용 SHA-256 해시를 만든다."""
        value = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(value.encode()).hexdigest()


class Result(BaseModel):
    """Agent가 결과 큐로 전달하는 공통 응답."""

    model_config = ConfigDict(extra="forbid")
    status: Status
    result_type: ResultType | None = None
    reasonCode: str
    summary: str
    diagnosis: str
    proposal: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    nextAction: str
    plan: Plan | None = None
    verification_ok: bool | None = None
    agent_mode: Literal["demo", "llm"] = "demo"

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_result(cls, value):
        # 이전 큐 메시지·체크포인트도 현재 상태 이름으로 읽는다.
        """이전 예산·안내·권한 완료 결과를 현재 상태와 결과 유형으로 맞춘다."""
        if isinstance(value, dict):
            value = dict(value)
            if value.get("status") == "ON_HOLD":
                value["status"] = "REJECTED"
            if value.get("reasonCode") == "INSUFFICIENT_BUDGET":
                value["reasonCode"] = "BUDGET_INSUFFICIENT"
            if "result_type" not in value:
                if (value.get("status") == "MANUAL_REVIEW"
                    and value.get("reasonCode") == "RAG_GUIDANCE"
                    and isinstance(value.get("proposal"), str) and value["proposal"].strip()
                    and value.get("plan") is None and value.get("verification_ok") is None):
                    value.update(status="DONE", result_type="GUIDANCE")
                elif value.get("status") == "DONE" and value.get("verification_ok") is True:
                    value["result_type"] = "ACCESS_VERIFIED"
        return value

    @model_validator(mode="after")
    def validate_completion(self):
        if self.status != Status.DONE:
            if self.result_type is not None:
                raise ValueError("Only DONE can have a result_type")
        elif self.result_type == ResultType.GUIDANCE:
            if not self.proposal.strip() or self.plan is not None or self.verification_ok is not None:
                raise ValueError("Guidance requires text and cannot claim a grant or verification")
        elif self.result_type != ResultType.ACCESS_VERIFIED or self.verification_ok is not True:
            raise ValueError("Access completion requires verification")
        return self


class Job(BaseModel):
    """worker가 RabbitMQ에서 받는 분석 또는 실행 작업."""

    model_config = ConfigDict(extra="forbid")
    event_id: str
    job_type: Literal["ANALYZE", "EXECUTE"]
    problem_id: str
    requester_id: str
    platform: Platform
    contents: str = Field(max_length=5000)
    idempotency_key: str | None = None
    plan_hash: str | None = None


class ToolFailure(RuntimeError):
    """도구 실패의 코드와 재시도 가능 여부를 노드까지 전달한다."""

    def __init__(self, code: str, message: str, retryable: bool = False, reason: str | None = None):
        """도구 실패의 공통 코드·메시지와 재시도 가능 여부를 저장한다."""
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.reason = reason
