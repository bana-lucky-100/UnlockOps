"""Agent와 MCP 서버가 공유하는 도구별 입력·응답 형식과 공통 오류 변환."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from .models import ToolFailure


# Annotated는 기본 타입에 길이·형식 검사 조건을 붙인다.
Text = Annotated[str, Field(strict=True, min_length=1)]
PlatformValue = Literal["GITHUB", "JIRA", "SLACK", "NOTION"]
GrantRole = Literal[
    "Read", "Write", "Viewer", "Developer", "Can view", "Can edit", "Member", "Seat"
]


def uuid_string(value: str) -> str:
    """유효한 UUID인지 확인하고 표준 문자열 형식으로 정규화한다."""
    return str(UUID(value))


UUIDString = Annotated[
    str,
    Field(strict=True, min_length=36, max_length=36, json_schema_extra={"format": "uuid"}),
    AfterValidator(uuid_string),
]
Query = Annotated[str, Field(strict=True, max_length=5000)]
Money = Annotated[str, Field(strict=True, pattern=r"^\d+(?:\.\d{1,2})?$")]


def boolean_only(value):
    # Literal만 사용하면 숫자 1/0도 통과할 수 있어 JSON 불리언인지 먼저 확인한다.
    """숫자 1·0 등의 자동 변환을 막고 실제 JSON 불리언만 허용한다."""
    if type(value) is not bool:
        raise ValueError("A JSON boolean is required")
    return value


TrueFlag = Annotated[Literal[True], BeforeValidator(boolean_only)]
FalseFlag = Annotated[Literal[False], BeforeValidator(boolean_only)]


class Input(BaseModel):
    # 알 수 없는 입력 필드와 자동 타입 변환을 허용하지 않는다.
    model_config = ConfigDict(extra="forbid", strict=True)


class EmployeeInput(Input):
    employee_id: UUIDString


class ResourceInput(EmployeeInput):
    resource_id: UUIDString


class ResolveInput(Input):
    platform: PlatformValue
    hint: Query


class AccessSearchInput(ResourceInput):
    query: Query


class AccessReadInput(Input):
    doc_id: Annotated[str, Field(pattern=r"^A-ACCESS-(03|04|07)$")]


class PolicySearchInput(Input):
    query: Query
    platform: PlatformValue
    limit: Annotated[int, Field(ge=1, le=10)] = 5


class PolicyReadInput(Input):
    doc_id: Annotated[str, Field(pattern=r"^(POL-\d{2}|(?:GH|JR|SL|NT)-OFF-\d{2})$")]
    article: Annotated[str, Field(max_length=100)] = ""


class GrantInput(Input):
    problem_id: UUIDString
    idempotency_key: Annotated[str, Field(min_length=1, max_length=200)]


class VerifyInput(ResourceInput):
    requested_role: GrantRole


class Output(BaseModel):
    # 핵심 필드는 엄격히 검사하고 출처·검색 점수 같은 추가 메타데이터는 보존한다.
    model_config = ConfigDict(extra="allow", strict=True)
    ok: TrueFlag = True


class EmployeeProfile(Output):
    id: Text
    employee_no: Text
    department_id: Text
    department_name: Text
    job_grade: Literal["사원", "대리", "과장", "차장", "부장"]
    job_family: Literal["DEV", "NON_DEV"]
    head_id: Text | None = None


class Resource(Output):
    id: Text
    external_id: Text
    name: Text
    platform: PlatformValue
    access_scope: Literal["GENERAL", "TF", "DEPARTMENT", "CONFIDENTIAL", "SEAT"]
    security_grade: Literal["GENERAL", "INTERNAL", "CONFIDENTIAL"] | None = None
    designated_department_id: Text | None = None
    owner_department_id: Text | None = None

    @model_validator(mode="after")
    def protected_resource(self):
        # 개별 필드 검사 후, 기밀·부서 자원에 필요한 관련 값도 확인한다.
        """기밀·부서 자원에 필요한 보안 등급과 담당 부서 정보가 있는지 확인한다."""
        if self.access_scope == "CONFIDENTIAL" and self.security_grade != "CONFIDENTIAL":
            raise ValueError("Confidential resource requires its classification")
        if self.security_grade == "CONFIDENTIAL" and not self.designated_department_id:
            raise ValueError("Confidential resource requires its designated department")
        if self.access_scope == "DEPARTMENT" and not self.owner_department_id:
            raise ValueError("Department resource requires its owner department")
        return self


class ResourceResolution(Output):
    matches: list[Resource]
    ambiguous: bool

    @model_validator(mode="after")
    def consistent_ambiguity(self):
        """후보가 정확히 하나인지와 ambiguous 표시가 일치하는지 확인한다."""
        if self.ambiguous != (len(self.matches) != 1):
            raise ValueError("Resource ambiguity does not match the candidates")
        return self


class Membership(Output):
    member: bool
    leader_id: Text | None = None


class CurrentPermissions(Output):
    role: Text | None
    can_browse: bool | None = None


class Budget(Output):
    remaining_monthly_amount: Money
    unit_monthly_price: Money

    @model_validator(mode="after")
    def positive_price(self):
        """좌석 단가가 0보다 큰 금액인지 확인한다."""
        if Decimal(self.unit_monthly_price) <= 0:
            raise ValueError("Seat price must be positive")
        return self


class BudgetResult(Output):
    budget: Budget | None


class EvidenceChunk(Output):
    chunk_id: Text
    doc_id: Text
    text: Text
    source: Text
    version: Text


class SearchResult(Output):
    hits: list[EvidenceChunk]


class AccessContext(Output):
    profile: EmployeeProfile
    resource_id: Text
    membership: Membership
    current: CurrentPermissions
    budget: Budget | None
    maximum_role: str


class AccessSearchResult(SearchResult):
    maximum_role: str
    context: AccessContext

    @model_validator(mode="after")
    def consistent_ceiling(self):
        if self.maximum_role != self.context.maximum_role:
            raise ValueError("Access ceilings must use the same context")
        return self


class DocumentResult(Output):
    chunks: list[EvidenceChunk]


class GrantResult(Output):
    ok: TrueFlag
    changed: bool
    role: GrantRole


class VerificationResult(Output):
    verified: bool
    ok: TrueFlag = True
    current: CurrentPermissions | None = None


class ErrorDetail(Input):
    code: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")]
    message: Annotated[str, Field(min_length=1, max_length=500)]
    retryable: bool
    reason: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")] | None = None


class ErrorResult(Input):
    ok: FalseFlag
    error: ErrorDetail


class LegacyError(Output):
    ok: FalseFlag
    error_code: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Z][A-Z0-9_]*$")]
    retryable: bool


# 도구 이름으로 동일한 입력·응답 모델을 찾아 서버와 클라이언트가 함께 사용한다.
INPUTS = {
    "get_employee_profile": EmployeeInput,
    "resolve_resource": ResolveInput,
    "get_tf_membership": ResourceInput,
    "get_current_permissions": ResourceInput,
    "check_budget": EmployeeInput,
    "search_access_rules": AccessSearchInput,
    "read_access_rule": AccessReadInput,
    "search_policy": PolicySearchInput,
    "read_policy": PolicyReadInput,
    "grant_permission": GrantInput,
    "verify_permission": VerifyInput,
}
OUTPUTS = {
    "get_employee_profile": EmployeeProfile,
    "resolve_resource": ResourceResolution,
    "get_tf_membership": Membership,
    "get_current_permissions": CurrentPermissions,
    "check_budget": BudgetResult,
    "search_access_rules": AccessSearchResult,
    "read_access_rule": DocumentResult,
    "search_policy": SearchResult,
    "read_policy": DocumentResult,
    "grant_permission": GrantResult,
    "verify_permission": VerificationResult,
}


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
            legacy = LegacyError.model_validate(data)
            raise ToolFailure(
                legacy.error_code, "Business operation was not applied", legacy.retryable
            )
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
