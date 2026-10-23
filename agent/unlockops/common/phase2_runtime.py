"""Shared v2 graph boundaries: tool scope, retries, deterministic event identity."""
from __future__ import annotations

import asyncio
from functools import wraps
from uuid import UUID, uuid5
from pydantic import ValidationError
from .models import ToolFailure
from .phase2 import AccessEvent, AccessJob, AccessView, ReclaimEvent, ReclaimJob, ReclaimRunView
from .contracts import validate_input, validate_output
from .settings import settings

ACCESS_READ = {"get_access_request_context", "assess_access_request", "search_workflow_policy", "read_workflow_policy"}
ACCESS_EXECUTE = {"get_access_request_context", "execute_access_plan", "verify_access_plan"}
RECLAIM_READ = {"get_reclaim_check_context", "list_revocation_candidates", "get_reclaim_notification_history", "search_workflow_policy", "read_workflow_policy"}


class Phase2Tools:
    def __init__(self, tools, job):
        self.tools, self.job, self.calls = tools, job, 0
        self.allowed = RECLAIM_READ if isinstance(job, ReclaimJob) else ACCESS_READ if job.job_type == "ANALYZE" else ACCESS_EXECUTE
        self.work_id = str(job.run_id if isinstance(job, ReclaimJob) else job.problem_id)

    async def call(self, name, arguments, *, retry=False):
        if name not in self.allowed:
            raise ToolFailure("TOOL_SCOPE", "Tool is not allowed for this v2 workflow")
        args = validate_input(name, arguments)
        for key in ("problem_id", "run_id", "work_id"):
            if key in args and args[key] != self.work_id:
                raise ToolFailure("REQUEST_SCOPE", "Cannot switch the work item")
        if "task_type" in args and args["task_type"] != self.job.task_type:
            raise ToolFailure("REQUEST_SCOPE", "Cannot switch workflow type")
        if "job_event_id" in args and args["job_event_id"] != str(self.job.event_id):
            raise ToolFailure("JOB_SCOPE", "Cannot switch the current job")
        if name in {"execute_access_plan", "verify_access_plan"}:
            if args["plan_hash"] != self.job.plan_hash or args["idempotency_key"] != self.job.idempotency_key:
                raise ToolFailure("PLAN_CHANGED", "Cannot switch execution authorization")
        attempts = settings.max_execution_attempts if retry else 1
        for attempt in range(attempts):
            if self.calls >= settings.max_tools:
                raise ToolFailure("TOOL_BUDGET", "v2 tool call limit reached")
            self.calls += 1
            try:
                return validate_output(name, await self.tools.call(name, args))
            except ToolFailure as error:
                if not error.retryable or attempt + 1 == attempts:
                    raise
                await asyncio.sleep(min(2 ** attempt, 2))


def guarded(node):
    @wraps(node)
    async def run(state, **kwargs):
        try:
            return await node(state, **kwargs)
        except ToolFailure as error:
            return {"error": {"code": error.code}, "events": state.get("events", []) + [{"node": node.__name__, "code": error.code}]}
        except (ValidationError, ValueError, KeyError, TypeError):
            return {"error": {"code": "INVALID_TOOL_OUTPUT"}}
    return run


def event_id(job):
    return uuid5(job.event_id, "v2-terminal-result")


def access_event(job, result, *, entitlement=None, evidence=None):
    return AccessEvent(schema_version=2, event_id=event_id(job), job_event_id=job.event_id,
        problem_id=job.problem_id, job_type=job.job_type,
        event_type="ANALYZED" if job.job_type == "ANALYZE" else "EXECUTED", result=result,
        proposed_entitlement_id=entitlement, policy_evidence=evidence or []).model_dump(mode="json")


def failure_event(job, code):
    if isinstance(job, ReclaimJob):
        review = code in {"POLICY_SOURCE_UNAVAILABLE", "SCAN_LIMIT", "MISSING_SOURCE_EVIDENCE"}
        result = ReclaimRunView(schema_version=2, run_id=job.run_id,
            status="MANUAL_REVIEW" if review else "FAILED",
            reason_code="MISSING_SOURCE_EVIDENCE" if review else "SCAN_FAILED",
            message="점검 근거·조회 범위를 확인해야 합니다." if review else "회수 점검 도구 호출에 실패했습니다.")
        return ReclaimEvent(schema_version=2, event_id=event_id(job), job_event_id=job.event_id,
            run_id=job.run_id, event_type="RECLAIM_CHECKED" if review else "FAILED", result=result).model_dump(mode="json")
    review = job.job_type == "ANALYZE" and code in {"POLICY_SOURCE_UNAVAILABLE", "MODEL_UNAVAILABLE", "OUT_OF_SCOPE"}
    result = AccessView(schema_version=2, problem_id=job.problem_id, status="MANUAL_REVIEW" if review else "FAILED",
        reason_code=("MODEL_UNAVAILABLE" if code == "MODEL_UNAVAILABLE" else "OUT_OF_SCOPE" if code == "OUT_OF_SCOPE" else "MISSING_SOURCE_EVIDENCE") if review else "TOOL_CALL_FAILED",
        message="분석에 필요한 근거 또는 요청 범위를 확인해야 합니다." if review else "분석 또는 실행 도구 호출에 실패했습니다.")
    return AccessEvent(schema_version=2, event_id=event_id(job), job_event_id=job.event_id,
        problem_id=job.problem_id, job_type=job.job_type, event_type="ANALYZED" if review else "FAILED", result=result).model_dump(mode="json")
