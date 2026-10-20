from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Platform(StrEnum):
    GITHUB = "GITHUB"
    JIRA = "JIRA"
    SLACK = "SLACK"
    NOTION = "NOTION"


class Status(StrEnum):
    RECEIVED = "RECEIVED"
    DIAGNOSING = "DIAGNOSING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    DONE = "DONE"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_hint: str = Field(default="", max_length=200)
    requested_role: str = Field(default="", max_length=100)
    symptom: str = Field(default="", max_length=500)
    out_of_scope: bool = False


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id: str
    requester_id: str
    platform: Platform
    resource_id: str
    resource_key: str
    requested_role: str

    def digest(self) -> str:
        value = json.dumps(self.model_dump(mode="json"), sort_keys=True,
                           ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(value.encode()).hexdigest()


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status
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
    def normalize_legacy_budget(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            if value.get("status") == "ON_HOLD": value["status"] = "REJECTED"
            if value.get("reasonCode") == "INSUFFICIENT_BUDGET":
                value["reasonCode"] = "BUDGET_INSUFFICIENT"
        return value


class Job(BaseModel):
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
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
