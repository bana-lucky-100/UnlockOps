"""Shared authenticated HTTP transport for workflow tools."""
import httpx
from pydantic import ValidationError
from unlockops.common.contracts import ErrorResult, ErrorDetail
from unlockops.common.models import ToolFailure
from unlockops.common.settings import settings


class BackendClient:
    """Spring HTTP 인증·응답·오류 처리를 공유한다. 실행·검증 응답은 캐시하지 않는다."""

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
