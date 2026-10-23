"""Validate frozen scan evidence and preserve it across optional narration."""
from hashlib import sha256

from ..common.workflow_contracts import ReclaimCandidate
from ..common.runtime import guarded
from ..common.models import ToolFailure
from .policy import _is_reclaim_clause


def verify_context(context):
    """Bind the declared policy hash to the actual frozen document contents."""
    policy = context.context.policy
    actual_hash = sha256(policy.content.encode()).hexdigest()
    if context.context.policy_hash != policy.source_hash or policy.source_hash != actual_hash:
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Frozen policy content and hash differ")


def verify_candidate(item, context, sections):
    """Check evidence identity; business classifications remain server decisions."""
    policy = context.context.policy
    for evidence in item.policy_evidence:
        cited = [text for heading, text in sections.items()
                 if heading == evidence.article or heading.startswith(evidence.article + " ")]
        if (evidence.source_hash != policy.source_hash or evidence.doc_id != policy.doc_id
                or evidence.version != str(policy.revision) or not evidence.text.strip()
                or not any(evidence.text in text for text in cited)):
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Candidate policy differs from snapshot")
    if not item.review_required and not any(_is_reclaim_clause(e.article) for e in item.policy_evidence):
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Confirmed row lacks the reclaim clause")
    for evidence in item.fact_evidence:
        if (evidence.record_id != str(item.assignment_id) or not evidence.source.strip()
                or evidence.observed_at > context.as_of):
            raise ToolFailure("FACT_SCOPE", "Candidate fact belongs to another assignment or snapshot time")
        if evidence.source == "reclaim_snapshot_items" and evidence.observed_at != context.as_of:
            raise ToolFailure("SNAPSHOT_MISMATCH", "Candidate fact belongs to another snapshot time")
    if item.candidate_status == "PENDING_REVIEW" and item.cost_impact.status != "ESTIMATED":
        raise ToolFailure("INVALID_TOOL_OUTPUT", "A pending candidate requires checked cost evidence")


@guarded
async def verify_reports(state):
    """Only explanation text and generation mode may differ after narration."""
    # Prefer the scan checkpoint, which the report writer does not own. Keep the
    # previous input name available for callers using this verifier on its own.
    originals = state.get("verified_targets", state.get("before_report_targets"))
    if originals is None:
        raise ToolFailure("REPORT_FACT_MISMATCH", "Checked scan rows are missing")
    supplied = state["targets"]
    if len(originals) != len(supplied):
        raise ToolFailure("REPORT_FACT_MISMATCH", "Narration changed the number of scan rows")
    mutable = {"explanation", "generation_mode"}
    notified = {row["assignment_id"] for row in state.get("history", [])
                if row["candidate_status"] == "PENDING_REVIEW" and row.get("notified_at")}
    for original, current in zip(originals, supplied):
        checked = ReclaimCandidate.model_validate(original)
        narrated = ReclaimCandidate.model_validate(current)
        before = checked.model_dump(mode="json", exclude=mutable)
        after = narrated.model_dump(mode="json", exclude=mutable)
        if before != after:
            raise ToolFailure("REPORT_FACT_MISMATCH", "Narration changed a verified decision or fact")
        if checked.explanation != narrated.explanation or checked.generation_mode != narrated.generation_mode:
            eligible = (checked.candidate_status == "PENDING_REVIEW" and not checked.review_required
                        and checked.notified_at is None and str(checked.assignment_id) not in notified)
            if not eligible or not 0 < len(narrated.explanation.strip()) <= 2000:
                raise ToolFailure("REPORT_FACT_MISMATCH", "Narration changed an ineligible row or produced invalid text")
    return {}
