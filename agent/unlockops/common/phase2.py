"""Version 2 contracts, routed through dedicated v2 worker graphs.

Workflow status is shared vocabulary; completion/approval invariants are task-specific.
The exported JSON Schema and fixtures are consumed by Java and TypeScript tests.
"""
from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Platform(StrEnum):
    SNOWFLAKE = "SNOWFLAKE"
    DATABRICKS = "DATABRICKS"
    SALESFORCE = "SALESFORCE"
    DATADOG = "DATADOG"
    TABLEAU_CLOUD = "TABLEAU_CLOUD"
    FIGMA = "FIGMA"
    GITHUB = "GITHUB"
    JIRA = "JIRA"
    SLACK = "SLACK"
    NOTION = "NOTION"


class TaskType(StrEnum):
    ACCESS_REQUEST = "ACCESS_REQUEST"
    RECLAIM_SCAN = "RECLAIM_SCAN"


class Status(StrEnum):
    RECEIVED = "RECEIVED"
    DIAGNOSING = "DIAGNOSING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    ON_HOLD = "ON_HOLD"
    EXECUTING = "EXECUTING"
    DONE = "DONE"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    WAITING = "WAITING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ON_HOLD = "ON_HOLD"
    SKIPPED = "SKIPPED"


class CandidateStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    RETAINED = "RETAINED"
    EXCLUDED = "EXCLUDED"


REASON_STATUSES = {
    "ELIGIBLE": "WAITING_APPROVAL", "LEAST_PRIVILEGE_PROPOSED": "WAITING_APPROVAL",
    "BUDGET_INSUFFICIENT": "ON_HOLD", "HELD_BY_APPROVER": "ON_HOLD",
    "HUMAN_APPROVED": "EXECUTING", "HUMAN_REJECTED": "REJECTED",
    "POLICY_NOT_ELIGIBLE": "REJECTED", "NOT_TF_MEMBER": "REJECTED", "DUPLICATE_SEAT": "REJECTED",
    "MISSING_SOURCE_EVIDENCE": "MANUAL_REVIEW", "APPROVER_UNAVAILABLE": "MANUAL_REVIEW",
    "OUT_OF_SCOPE": "MANUAL_REVIEW", "BUDGET_UNAVAILABLE": "MANUAL_REVIEW", "MODEL_UNAVAILABLE": "MANUAL_REVIEW",
    "PLAN_REVIEW_REQUIRED": "MANUAL_REVIEW", "ANALYSIS_CONFLICT": "MANUAL_REVIEW",
    "VERIFIED": "DONE", "ALREADY_HAS_ACCESS": "DONE", "RAG_GUIDANCE": "DONE",
    "SCAN_IN_PROGRESS": "EXECUTING", "SCAN_COMPLETED": "DONE", "NO_NEW_CANDIDATES": "DONE",
    "VERIFICATION_FAILED": "FAILED", "TOOL_CALL_FAILED": "FAILED", "SCAN_FAILED": "FAILED", "NOTIFICATION_FAILED": "FAILED",
}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


Money = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,9})\.[0-9]{2}$")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Reason = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,99}$")]


class ApprovalStep(Contract):
    step: int = Field(ge=1)
    approver_id: UUID
    status: ApprovalStatus
    reason: str | None = None
    acted_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_decision(self):
        decided = self.status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.ON_HOLD}
        if decided != (self.acted_at is not None):
            raise ValueError("Only an actual decision has acted_at")
        if self.status in {ApprovalStatus.REJECTED, ApprovalStatus.ON_HOLD} and not (self.reason or "").strip():
            raise ValueError("Rejection/hold requires a reason")
        if self.status in {ApprovalStatus.PENDING, ApprovalStatus.WAITING} and self.reason is not None:
            raise ValueError("Unprocessed steps have no reason")
        return self


class GrantPlanV2(Contract):
    """All executable meaning is bound to immutable revision references.

Money is a decimal string; ids are normalized UUIDs; approver order is significant.
No free-form model-generated text participates in canonical hashing.
"""
    schema_version: Literal[2]
    problem_id: UUID
    company_id: UUID
    requester_id: UUID
    platform: Platform
    resource_id: UUID
    entitlement_id: UUID
    entitlement_revision: int = Field(ge=1)
    pricing_id: UUID
    pricing_revision: int = Field(ge=1)
    monthly_amount: Money
    currency: Currency
    cost_basis: Literal["SEAT_MONTHLY", "USAGE_ESTIMATE", "NO_ADDITIONAL_COST"]
    policy_id: UUID
    policy_revision: int = Field(ge=1)
    route_id: UUID
    route_revision: int = Field(ge=1)
    approver_ids: list[UUID] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_approvers(self):
        if self.requester_id in self.approver_ids or len(set(self.approver_ids)) != len(self.approver_ids):
            raise ValueError("Self approval and duplicate approvers are forbidden")
        if self.cost_basis == "NO_ADDITIONAL_COST" and self.monthly_amount != "0.00":
            raise ValueError("No additional cost must be zero")
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class WorkflowView(Contract):
    schema_version: Literal[2]
    task_type: TaskType
    status: Status
    reason_code: Reason | None = None
    message: str = Field(min_length=1)
    current_step: int | None = Field(default=None, ge=1)
    total_steps: int = Field(default=0, ge=0)
    approval_steps: list[ApprovalStep] = Field(default_factory=list)
    verification_ok: bool | None = None

    @model_validator(mode="after")
    def validate_common(self):
        expected_status = REASON_STATUSES.get(self.reason_code)
        if expected_status is not None and self.status != expected_status:
            raise ValueError("Reason and status disagree")
        if self.status not in {Status.RECEIVED, Status.DIAGNOSING} and self.reason_code is None:
            raise ValueError("A reason is required outside reception/diagnosis")
        if self.total_steps != len(self.approval_steps):
            raise ValueError("total_steps must match approval_steps")
        if [s.step for s in self.approval_steps] != list(range(1, self.total_steps + 1)):
            raise ValueError("Approval steps must be consecutive and ordered")
        if len({s.approver_id for s in self.approval_steps}) != self.total_steps:
            raise ValueError("Approval actors must be distinct")
        waiting = [s.step for s in self.approval_steps if s.status == ApprovalStatus.WAITING]
        if self.status == Status.WAITING_APPROVAL:
            if waiting != [self.current_step] or self.current_step is None:
                raise ValueError("Exactly the current step must be waiting")
            for s in self.approval_steps:
                expected = ApprovalStatus.APPROVED if s.step < self.current_step else (
                    ApprovalStatus.WAITING if s.step == self.current_step else ApprovalStatus.PENDING)
                if s.status != expected:
                    raise ValueError("A later step cannot bypass an earlier approval")
        elif waiting or self.current_step is not None:
            raise ValueError("current_step and WAITING only exist while waiting for approval")
        if self.task_type == TaskType.RECLAIM_SCAN:
            if self.status in {Status.WAITING_APPROVAL, Status.ON_HOLD, Status.REJECTED, Status.MANUAL_REVIEW}:
                raise ValueError("Reclaim scans do not enter approval states")
            if self.total_steps or self.verification_ok is not None:
                raise ValueError("Reclaim scans have no approvals or grant verification")
        return self


class AccessView(WorkflowView):
    task_type: Literal[TaskType.ACCESS_REQUEST] = TaskType.ACCESS_REQUEST
    problem_id: UUID
    result_type: Literal["GUIDANCE", "ACCESS_VERIFIED"] | None = None
    plan_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    plan_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_access(self):
        if (self.status == Status.DONE) != (self.result_type is not None):
            raise ValueError("Only DONE has a result_type")
        if self.result_type == "ACCESS_VERIFIED":
            if self.verification_ok is not True or self.reason_code != "VERIFIED":
                raise ValueError("Grant completion requires independent successful verification")
        elif self.result_type == "GUIDANCE":
            if self.verification_ok is not None or self.reason_code not in {"RAG_GUIDANCE", "ALREADY_HAS_ACCESS"}:
                raise ValueError("Guidance cannot claim a grant")
        if self.status == Status.EXECUTING or self.result_type == "ACCESS_VERIFIED":
            if not self.approval_steps or any(s.status != ApprovalStatus.APPROVED for s in self.approval_steps):
                raise ValueError("All required approvals must be complete")
        if self.verification_ok is True and self.result_type != "ACCESS_VERIFIED":
            raise ValueError("Verification success belongs only to verified grant completion")
        if (self.reason_code == "VERIFICATION_FAILED") != (self.verification_ok is False):
            raise ValueError("Only confirmed verification mismatch is false; lookup failure is null")
        return self


class ReclaimSummary(Contract):
    needs_review_count: int = Field(ge=0)
    new_candidate_count: int = Field(ge=0)
    pending_notification_count: int = Field(ge=0)


class NeedsReviewItem(Contract):
    assignment_id: UUID
    employee_name: str
    resource_name: str
    missing: list[Literal["USAGE_OBSERVATION", "PRICE_EVIDENCE", "EMPLOYMENT_STATUS", "RECLAIM_FACTS"]] = Field(min_length=1)


class ReclaimRunView(WorkflowView):
    task_type: Literal[TaskType.RECLAIM_SCAN] = TaskType.RECLAIM_SCAN
    run_id: UUID
    snapshot_id: UUID | None = None
    as_of: AwareDatetime | None = None
    scan_complete: bool = False
    needs_review_count: int = Field(default=0, ge=0)
    new_candidate_count: int = Field(default=0, ge=0)
    pending_notification_count: int = Field(default=0, ge=0)
    summary: ReclaimSummary | None = None
    needs_review: list[NeedsReviewItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scan(self):
        if (self.snapshot_id is None) != (self.as_of is None):
            raise ValueError("Snapshot id and as_of travel together")
        if self.scan_complete and self.snapshot_id is None:
            raise ValueError("A completed scan needs a snapshot")
        if self.summary is not None and (self.summary.needs_review_count, self.summary.new_candidate_count, self.summary.pending_notification_count) != (self.needs_review_count, self.new_candidate_count, self.pending_notification_count):
            raise ValueError("Summary differs from scan counts")
        if self.status == Status.DONE:
            if not self.scan_complete or self.pending_notification_count:
                raise ValueError("Incomplete scan/notification cannot be DONE")
            if self.reason_code not in {"SCAN_COMPLETED", "NO_NEW_CANDIDATES"}:
                raise ValueError("Invalid scan completion reason")
            if self.reason_code == "NO_NEW_CANDIDATES" and (self.new_candidate_count or self.needs_review_count):
                raise ValueError("Candidates or additional checks cannot be reported as none")
        return self


class PolicyEvidence(Contract):
    doc_id: str = Field(min_length=1)
    article: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_hash: Hash
    text: str = Field(min_length=1)


class FactEvidence(Contract):
    source: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    observed_at: AwareDatetime


class CostImpact(Contract):
    status: Literal["ESTIMATED", "UNKNOWN"]
    monthly_amount: Money | None = None
    currency: Currency | None = None
    basis: Literal["SYNTHETIC_CONTRACT", "CONTRACT", "PUBLIC_LIST_PRICE"] | None = None

    @model_validator(mode="after")
    def validate_cost(self):
        if self.status == "ESTIMATED" and (self.monthly_amount is None or self.currency is None or self.basis is None):
            raise ValueError("Estimated cost needs amount, currency and basis")
        if self.status == "UNKNOWN" and self.monthly_amount is not None:
            raise ValueError("Unknown cost is null, never zero")
        return self


class ReclaimCandidate(Contract):
    assignment_id: UUID
    target_id: UUID | None = None
    episode_id: UUID | None = None
    platform: Platform
    candidate_status: CandidateStatus | None = None
    candidate_reason_code: Literal["TF_ENDED_UNUSED_30D", "EMPLOYEE_LEFT"] | None = None
    exclusion_reason_code: Literal["ACTIVE_OTHER_TF", "RETENTION_APPROVED", "USAGE_RESUMED"] | None = None
    skip_reason_code: Literal["ALREADY_NOTIFIED"] | None = None
    review_required: bool = False
    notified_at: AwareDatetime | None = None
    read_at: AwareDatetime | None = None
    action_taken: Literal["NONE"] = "NONE"
    generation_mode: Literal["template", "llm"] = "template"
    explanation: str = Field(min_length=1)
    policy_evidence: list[PolicyEvidence] = Field(default_factory=list)
    fact_evidence: list[FactEvidence] = Field(default_factory=list)
    cost_impact: CostImpact

    @model_validator(mode="after")
    def validate_candidate(self):
        if not self.review_required and (not self.policy_evidence or not self.fact_evidence):
            raise ValueError("A confirmed decision requires policy and fact evidence")
        if self.review_required != (self.candidate_status is None):
            raise ValueError("An unconfirmed row must require review")
        if (self.target_id is None) != (self.episode_id is None):
            raise ValueError("Target and episode identity must travel together")
        if self.candidate_status == CandidateStatus.PENDING_REVIEW:
            if self.candidate_reason_code is None or self.exclusion_reason_code is not None:
                raise ValueError("Pending candidate requires a selection reason only")
        if self.candidate_status == CandidateStatus.RETAINED and self.exclusion_reason_code != "RETENTION_APPROVED":
            raise ValueError("Retained requires an approved retention exception")
        if self.candidate_status == CandidateStatus.EXCLUDED and self.exclusion_reason_code not in {"ACTIVE_OTHER_TF", "USAGE_RESUMED"}:
            raise ValueError("Excluded requires a verified exclusion reason")
        if self.skip_reason_code and (self.notified_at is None or self.episode_id is None or self.candidate_status != CandidateStatus.PENDING_REVIEW):
            raise ValueError("Already notified requires the existing pending episode and delivery time")
        if self.read_at is not None and self.notified_at is None:
            raise ValueError("Reading does not substitute for delivery")
        return self


class AccessJob(Contract):
    schema_version: Literal[2]
    event_id: UUID
    task_type: Literal[TaskType.ACCESS_REQUEST] = TaskType.ACCESS_REQUEST
    job_type: Literal["ANALYZE", "EXECUTE"]
    problem_id: UUID
    plan_hash: Hash | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=150)

    @model_validator(mode="after")
    def execution_identity(self):
        if self.job_type == "EXECUTE" and (self.plan_hash is None or self.idempotency_key is None):
            raise ValueError("Execution requires approved plan hash and execution key")
        if self.job_type == "ANALYZE" and (self.plan_hash is not None or self.idempotency_key is not None):
            raise ValueError("Analysis cannot carry execution authorization")
        return self


class ReclaimJob(Contract):
    schema_version: Literal[2]
    event_id: UUID
    task_type: Literal[TaskType.RECLAIM_SCAN] = TaskType.RECLAIM_SCAN
    job_type: Literal["RECLAIM_CHECK"] = "RECLAIM_CHECK"
    run_id: UUID
    trigger: Literal["DAILY_SCHEDULE", "MANUAL_DEMO"]
    scope_key: str = Field(min_length=1, max_length=200)
    scheduled_for: AwareDatetime


class AccessEvent(Contract):
    schema_version: Literal[2]
    event_id: UUID
    job_event_id: UUID
    proposed_entitlement_id: UUID | None = None
    policy_evidence: list[PolicyEvidence] = Field(default_factory=list)
    task_type: Literal[TaskType.ACCESS_REQUEST] = TaskType.ACCESS_REQUEST
    problem_id: UUID
    job_type: Literal["ANALYZE", "EXECUTE"]
    event_type: Literal["PROGRESS", "ANALYZED", "EXECUTED", "FAILED"]
    result: AccessView

    @model_validator(mode="after")
    def identity(self):
        if self.problem_id != self.result.problem_id:
            raise ValueError("Result problem differs from envelope")
        if (self.event_type == "ANALYZED" and self.job_type != "ANALYZE") or (self.event_type == "EXECUTED" and self.job_type != "EXECUTE"):
            raise ValueError("Job and event type mismatch")
        if self.event_type == "EXECUTED":
            if self.result.status not in {Status.DONE, Status.FAILED}:
                raise ValueError("Execution must return a terminal execution result")
            if self.result.status == Status.DONE and self.result.result_type != "ACCESS_VERIFIED":
                raise ValueError("Executed cannot complete as guidance")
        if self.event_type == "ANALYZED" and self.result.result_type == "ACCESS_VERIFIED":
            raise ValueError("Analysis cannot claim execution completion")
        if self.event_type == "FAILED" and self.result.status != Status.FAILED:
            raise ValueError("Failed event must carry a failed result")
        return self


class ReclaimEvent(Contract):
    schema_version: Literal[2]
    event_id: UUID
    job_event_id: UUID
    task_type: Literal[TaskType.RECLAIM_SCAN] = TaskType.RECLAIM_SCAN
    run_id: UUID
    event_type: Literal["PROGRESS", "RECLAIM_CHECKED", "FAILED"]
    result: ReclaimRunView
    targets: list[ReclaimCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def identity(self):
        if self.run_id != self.result.run_id:
            raise ValueError("Result run differs from envelope")
        if self.result.status == Status.DONE:
            raise ValueError("Only Spring may finalize storage and delivery as DONE")
        if self.event_type == "RECLAIM_CHECKED" and self.result.status == Status.EXECUTING:
            if not self.result.scan_complete or self.result.needs_review_count != sum(t.review_required for t in self.targets):
                raise ValueError("Incomplete scan or inconsistent review count")
        if self.event_type == "FAILED" and self.result.status != Status.FAILED:
            raise ValueError("Failed event must carry a failed result")
        if len({t.assignment_id for t in self.targets}) != len(self.targets):
            raise ValueError("Duplicate assignment in a scan result")
        return self


class ReclaimContextRequest(Contract):
    run_id: UUID


class CandidatePageRequest(ReclaimContextRequest):
    policy_hash: Hash
    cursor: str | None = Field(default=None, max_length=500)


class NotificationHistoryRequest(ReclaimContextRequest):
    assignment_ids: list[UUID] = Field(min_length=1, max_length=200)


class CandidatePage(Contract):
    run_id: UUID
    snapshot_id: UUID
    as_of: AwareDatetime
    expected_count: int = Field(ge=0)
    next_cursor: str | None = None
    items: list[ReclaimCandidate]


class AccessRequestInput(Contract):
    schema_version: Literal[2]
    platform: Platform
    contents: str = Field(min_length=1, max_length=5000)
    resource_id: UUID | None = None
    entitlement_id: UUID | None = None


class ApprovalDecisionInput(Contract):
    action: Literal["APPROVE", "REJECT", "HOLD"]
    expected_plan_hash: Hash
    expected_plan_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def reason_required(self):
        if self.action != "APPROVE" and not (self.reason or "").strip():
            raise ValueError("Rejection and hold require a reason")
        return self


class ReclaimStartInput(Contract):
    scope_id: UUID


class ContractBundle(Contract):
    """Schema export root. Each field is also independently reusable by its $def."""
    plan: GrantPlanV2
    access_view: AccessView
    reclaim_view: ReclaimRunView
    job: Annotated[AccessJob | ReclaimJob, Field(discriminator="task_type")]
    event: Annotated[AccessEvent | ReclaimEvent, Field(discriminator="task_type")]
    context_request: ReclaimContextRequest
    candidate_page_request: CandidatePageRequest
    notification_history_request: NotificationHistoryRequest
    candidate_page: CandidatePage
    access_request: AccessRequestInput
    approval_decision: ApprovalDecisionInput
    reclaim_start: ReclaimStartInput
