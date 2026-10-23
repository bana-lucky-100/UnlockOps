"""Business MCP의 업무 조회·변경을 Spring 내부 API로 전달한다. DB에 연결하지 않는다."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from unlockops.common.contracts import (
    Budget, CurrentPermissions, EmployeeProfile, ErrorDetail, ErrorResult,
    Membership, TrueFlag, UUIDString, validate_output,
)
from unlockops.common.models import ToolFailure
from unlockops.common.settings import settings


class ContextResponse(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    profile: EmployeeProfile
    resource_id: UUIDString | None = None
    membership: Membership | None = None
    current: CurrentPermissions | None = None
    maximum_role: str | None = None
    budget: Budget | None = None
    rule_source: str | None = None
    source_hashes: dict[str, str] = {}


class VerificationResponse(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    ok: TrueFlag
    verified: bool
    current: CurrentPermissions


class BackendClient:
    """기존 MCP 도구 입력을 Spring DTO로 변환한다. 실행·검증 응답은 캐시하지 않는다."""

    def __init__(self, client: httpx.Client | None = None, *, base_url=None, token=None):
        self.client = client
        self.base_url = (settings.backend_url if base_url is None else base_url).rstrip("/")
        self.token = settings.internal_api_token if token is None else token
        try:
            url = httpx.URL(self.base_url)
            valid = url.scheme in {"http", "https"} and url.host and not url.userinfo and not url.query and not url.fragment
        except (httpx.InvalidURL, ValueError):
            valid = False
        if not valid:
            raise ToolFailure("BACKEND_CONFIGURATION_ERROR", "Invalid internal API configuration")

    def _post(self, path, payload):
        return self._request("POST", path, payload)

    def _request(self, method, path, payload=None, *, object_response=True):
        if not self.token or not self.token.strip():
            raise ToolFailure("BACKEND_AUTH_FAILED", "Internal API service token is missing")
        try:
            if self.client is None:
                with httpx.Client(timeout=10, follow_redirects=False) as client:
                    response = client.request(method, self.base_url + path, json=payload,
                        headers={"Authorization": "Bearer " + self.token})
            else:
                response = self.client.request(method, self.base_url + path, json=payload,
                    headers={"Authorization": "Bearer " + self.token}, timeout=10, follow_redirects=False)
        except httpx.TimeoutException:
            raise ToolFailure("UPSTREAM_TIMEOUT", "Spring internal API timed out", True) from None
        except (httpx.TransportError, OSError):
            raise ToolFailure("UPSTREAM_UNAVAILABLE", "Spring internal API is unavailable", True) from None
        try:
            data = response.json()
        except ValueError:
            data = None
        if not 200 <= response.status_code < 300:
            self._error(response.status_code, data)
        if object_response and not isinstance(data, dict):
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Internal API response must be a JSON object")
        if isinstance(data, dict) and (data.get("ok") is False or "error" in data or "error_code" in data):
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Internal API success contains an error")
        return data

    def _error(self, status, data):
        if status in {401, 403}:
            raise ToolFailure("BACKEND_AUTH_FAILED", "Spring service authentication failed")
        try:
            error = None
            if isinstance(data, dict) and ("error" in data or data.get("ok") is False):
                error = ErrorResult.model_validate(data).error
            elif isinstance(data, dict) and "code" in data:
                error = ErrorDetail.model_validate(data)
            if error is not None:
                # 제공자 응답 원문·SQL·URL·토큰을 모델에 전달하지 않는다.
                raise ToolFailure(error.code, "Spring internal API rejected the operation", error.retryable, error.reason)
        except ValidationError:
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Internal API error response is invalid") from None
        code = {400: "INVALID_TOOL_INPUT", 404: "NOT_FOUND", 409: "BACKEND_CONFLICT"}.get(status, "BACKEND_HTTP_ERROR")
        retryable = status in {408, 429} or status >= 500
        if retryable:
            code = "UPSTREAM_UNAVAILABLE"
        raise ToolFailure(code, "Spring internal API request failed", retryable)

    def _context(self, employee_id, resource_id=None, *, include_budget=False):
        payload = {"employeeId": employee_id}
        if resource_id is not None:
            payload["resourceId"] = resource_id
        if include_budget:
            payload["includeBudget"] = True
        data = self._post("/internal/access-context", payload)
        try:
            parsed = ContextResponse.model_validate(data)
        except ValidationError:
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Internal access context is invalid") from None
        if parsed.profile.id != employee_id:
            raise ToolFailure("EMPLOYEE_SCOPE", "Internal API returned another employee")
        if resource_id is not None:
            if parsed.resource_id != resource_id:
                raise ToolFailure("RESOURCE_SCOPE", "Internal API returned another resource")
            if parsed.membership is None or parsed.current is None or parsed.maximum_role is None:
                raise ToolFailure("INVALID_TOOL_OUTPUT", "Required access facts are missing")
        return data

    def profile(self, employee_id):
        return self._context(employee_id)["profile"]

    def resolve(self, platform, hint):
        result = validate_output("resolve_resource", self._post("/internal/resources/resolve", {"platform": platform, "hint": hint}))
        if any(resource["platform"] != platform for resource in result["matches"]):
            raise ToolFailure("PLATFORM_SCOPE", "Internal API returned another platform")
        return result

    def membership(self, employee_id, resource_id):
        return self._context(employee_id, resource_id)["membership"]

    def current(self, employee_id, resource_id):
        return self._context(employee_id, resource_id)["current"]

    def budget(self, employee_id):
        data = self._context(employee_id, include_budget=True)
        if "budget" not in data:
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Budget lookup result is missing")
        return data["budget"]

    def access_rules(self, employee_id, resource_id):
        return self._context(employee_id, resource_id)

    def grant(self, problem_id, idempotency_key):
        return validate_output("grant_permission", self._post(f"/internal/problems/{problem_id}/grant",
            {"idempotencyKey": idempotency_key}))

    def verify(self, employee_id, resource_id, requested_role):
        result = self._post("/internal/access-verifications", {"employeeId": employee_id,
            "resourceId": resource_id, "requestedRole": requested_role})
        try:
            VerificationResponse.model_validate(result)
        except ValidationError:
            raise ToolFailure("INVALID_TOOL_OUTPUT", "Internal verification response is invalid") from None
        return validate_output("verify_permission", result)
