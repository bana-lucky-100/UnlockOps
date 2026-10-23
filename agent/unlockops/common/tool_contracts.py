"""v2 MCP wire contracts. Business facts come from Spring, not an agent-side DB."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from .workflow_contracts import (
    AccessView, CandidatePage, CandidatePageRequest, Contract, GrantPlanV2, Hash,
    Money, Currency, NotificationHistoryRequest, Platform, PolicyEvidence,
    ReclaimContextRequest, Status, TaskType,
)


class Row(BaseModel):
    # DB-backed context rows may acquire columns; expose only explicitly declared facts.
    model_config = ConfigDict(extra="ignore")


class AccessContextInput(Contract):
    problem_id: UUID


class AssessmentInput(AccessContextInput):
    job_event_id: UUID
    entitlement_id: UUID


class ExecutionInput(AccessContextInput):
    job_event_id: UUID
    plan_hash: Hash
    idempotency_key: str = Field(min_length=1, max_length=150)


class PolicyWorkInput(Contract):
    task_type: TaskType
    work_id: UUID
    source_hash: Hash | None = None


class PolicySearchInput(PolicyWorkInput):
    query: str = Field(min_length=1, max_length=5000)
    limit: int = Field(default=5, ge=1, le=10, strict=True)


class PolicyReadInput(PolicyWorkInput):
    source_hash: Hash
    article: str = Field(default="", max_length=200)


class PolicyRevision(Row):
    policy_id: UUID
    company_id: UUID
    revision: int = Field(ge=1)
    doc_id: str = Field(min_length=1)
    article: str = Field(min_length=1)
    source_hash: Hash
    content: str = Field(min_length=1)


class RequestRow(Row):
    id: UUID
    company_id: UUID
    requester_id: UUID
    platform: Platform
    contents: str = Field(min_length=1, max_length=5000)
    status: Status
    active_job_event_id: UUID
    requested_entitlement_id: UUID | None = None
    resource_id: UUID | None = None
    plan: GrantPlanV2 | None = None
    plan_hash: Hash | None = None
    approved_plan_hash: Hash | None = None
    idempotency_key: str | None = None


class EmployeeFacts(Row):
    id: UUID
    company_id: UUID
    department_id: UUID
    employment_status: Literal["ACTIVE", "LEFT", "UNKNOWN"]
    job_grade: str
    job_family: str


class EntitlementOption(Row):
    id: UUID
    code: str
    kind: Literal["ROLE", "PERMISSION_SET", "MEMBERSHIP", "SEAT"]
    resource_id: UUID
    name: str
    external_id: str
    platform: Platform


class SaasFacts(Row):
    company_id: UUID
    user_id: UUID
    platform: Platform
    account_exists: bool | None = None
    license_active: bool | None = None
    data_access: bool | None = None
    work_scope_assigned: bool | None = None
    job_function: str
    observed_at: AwareDatetime
    source_reference: str


class AccessContext(Contract):
    schema_version: Literal[2]
    problem: RequestRow
    requester: EmployeeFacts
    entitlements: list[EntitlementOption]
    facts: list[SaasFacts]
    policies: list[PolicyRevision]
    workflow: AccessView

    @model_validator(mode="after")
    def scope(self):
        p = self.problem
        if self.requester.id != p.requester_id or self.requester.company_id != p.company_id or self.workflow.problem_id != p.id:
            raise ValueError("Requester/company/workflow mismatch")
        if any(x.company_id != p.company_id for x in self.policies):
            raise ValueError("Policy company mismatch")
        if any(x.company_id != p.company_id or x.user_id != p.requester_id or x.platform != p.platform for x in self.facts):
            raise ValueError("Fact scope mismatch")
        if any(x.platform != p.platform for x in self.entitlements):
            raise ValueError("Entitlement platform mismatch")
        return self


class AccessCostFacts(Contract):
    operation: Literal['PERMISSION_ONLY', 'PURCHASE_SEAT', 'USAGE_ALLOCATION']
    unit_monthly_amount: Money
    incremental_monthly_amount: Money | None
    budget_monthly_amount: Money
    cost_basis: Literal['NO_ADDITIONAL_COST', 'SEAT_MONTHLY', 'USAGE_ESTIMATE']
    billing_scope: str | None
    license_code: str | None
    license_coverage: Literal['COVERED', 'NOT_COVERED', 'NOT_REQUIRED']
    license_observed_at: AwareDatetime | None
    license_source_reference: str | None

    @model_validator(mode='after')
    def amounts(self):
        if self.cost_basis == 'NO_ADDITIONAL_COST' and (Decimal(self.budget_monthly_amount) != 0 or self.incremental_monthly_amount != '0.00'):
            raise ValueError('No additional cost must be zero')
        if self.operation == 'PERMISSION_ONLY' and self.cost_basis != 'NO_ADDITIONAL_COST':
            raise ValueError('Permission-only cannot buy a seat')
        if self.operation == 'USAGE_ALLOCATION' and (self.cost_basis != 'USAGE_ESTIMATE' or self.incremental_monthly_amount is not None):
            raise ValueError('Usage allocation is not an invoice')
        return self


class AccessReviewFacts(Contract):
    """A server observation, never a price or TF membership inferred from policy text."""
    checked_at: AwareDatetime
    resource_name: str
    entitlement_code: str
    entitlement_kind: Literal["ROLE", "PERMISSION_SET", "MEMBERSHIP", "SEAT"]
    access_scope: Literal["GENERAL", "TF", "DEPARTMENT", "CONFIDENTIAL", "SEAT"]
    tf_member: bool | None
    monthly_amount: Money
    currency: Currency
    remaining_budget: Money
    price_source_kind: Literal["SYNTHETIC_CONTRACT", "CONTRACT", "PUBLIC_LIST_PRICE"]
    cost_assessment: AccessCostFacts | None = None


class Assessment(Contract):
    status: Status
    reason: str
    message: str = Field(min_length=1)
    plan: GrantPlanV2 | None = None
    evidence: list[PolicyEvidence]
    review_facts: AccessReviewFacts | None = None

    @model_validator(mode="after")
    def plan_required(self):
        if (self.status == Status.WAITING_APPROVAL) != (self.plan is not None):
            raise ValueError("Only approval assessment carries a plan")
        if self.plan and not self.evidence:
            raise ValueError("Plan requires source evidence")
        if self.plan and self.review_facts and (
            self.plan.monthly_amount != self.review_facts.monthly_amount
            or self.plan.currency != self.review_facts.currency
        ):
            raise ValueError("Report facts differ from the approved plan")
        if self.review_facts:
            cost = self.review_facts.cost_assessment
            if cost and (cost.budget_monthly_amount != self.review_facts.monthly_amount
                         or self.plan and cost.cost_basis != self.plan.cost_basis):
                raise ValueError('Cost assessment differs from the approved budget')
            enough = Decimal(self.review_facts.remaining_budget) >= Decimal(self.review_facts.monthly_amount)
            if self.status == Status.WAITING_APPROVAL and (not enough or (
                self.review_facts.access_scope == "TF" and self.review_facts.tf_member is not True
            )):
                raise ValueError("Approval contradicts observed budget or TF membership")
            if self.reason == "BUDGET_INSUFFICIENT" and enough:
                raise ValueError("Budget hold contradicts observed balance")
        return self


class ExecutionReceipt(Contract):
    executed: bool = Field(strict=True)
    schema_version: Literal[2] | None = None
    problem_id: UUID | None = None
    assignment_id: UUID | None = None
    plan_hash: Hash | None = None
    idempotency_key: str | None = None
    charged_amount: Money | None = None
    currency: Currency | None = None
    reason_code: Literal["PLAN_REVIEW_REQUIRED"] | None = None

    @model_validator(mode="after")
    def receipt(self):
        if self.executed:
            if any(x is None for x in (self.schema_version, self.problem_id, self.assignment_id, self.plan_hash, self.idempotency_key, self.charged_amount, self.currency)) or self.reason_code:
                raise ValueError("Incomplete execution receipt")
        elif self.reason_code != "PLAN_REVIEW_REQUIRED":
            raise ValueError("Unexplained admission failure")
        return self


class Verification(Contract):
    schema_version: Literal[2]
    problem_id: UUID
    receipt_exists: bool = Field(strict=True)
    verification_ok: bool | None = Field(strict=True)
    source: Literal["mock_entitlement_memberships"]

    @model_validator(mode="after")
    def receipt(self):
        if self.receipt_exists != (self.verification_ok is not None):
            raise ValueError("Missing receipt is unknown, not a verified mismatch")
        return self


class FrozenContext(Contract):
    policy: PolicyRevision
    rules: list[dict]
    policy_hash: Hash


class ReclaimContext(Contract):
    schema_version: Literal[2]
    run_id: UUID
    job_event_id: UUID
    snapshot_id: UUID
    as_of: AwareDatetime
    expected_count: int = Field(ge=0)
    context: FrozenContext


class Notification(Row):
    id: UUID
    recipient_id: UUID
    channel: str
    delivery_status: Literal["PENDING", "DELIVERED", "FAILED"]
    delivered_at: AwareDatetime | None = None
    read_at: AwareDatetime | None = None


class NotificationEpisode(Contract):
    assignment_id: UUID
    target_id: UUID
    episode_id: UUID
    candidate_status: Literal["PENDING_REVIEW", "RETAINED", "EXCLUDED"]
    notified_at: AwareDatetime | None = None
    notifications: list[Notification]


class NotificationHistory(Contract):
    items: list[NotificationEpisode]


class PolicyResult(Contract):
    source_hash: Hash
    evidence: list[PolicyEvidence]
    retrieval_mode: Literal["local-tfidf", "exact"]


INPUTS = {
    "get_access_request_context": AccessContextInput,
    "assess_access_request": AssessmentInput,
    "execute_access_plan": ExecutionInput,
    "verify_access_plan": ExecutionInput,
    "get_reclaim_check_context": ReclaimContextRequest,
    "list_revocation_candidates": CandidatePageRequest,
    "get_reclaim_notification_history": NotificationHistoryRequest,
    "search_workflow_policy": PolicySearchInput,
    "read_workflow_policy": PolicyReadInput,
}
OUTPUTS = {
    "get_access_request_context": AccessContext,
    "assess_access_request": Assessment,
    "execute_access_plan": ExecutionReceipt,
    "verify_access_plan": Verification,
    "get_reclaim_check_context": ReclaimContext,
    "list_revocation_candidates": CandidatePage,
    "get_reclaim_notification_history": NotificationHistory,
    "search_workflow_policy": PolicyResult,
    "read_workflow_policy": PolicyResult,
}
