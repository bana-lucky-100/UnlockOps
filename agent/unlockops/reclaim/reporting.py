"""Compose explanations, then project the S-04 report and wire event."""
import json
from collections.abc import Mapping
from copy import deepcopy
from importlib.resources import files

from ..common.workflow_contracts import ReclaimCandidate, ReclaimEvent
from ..common.runtime import guarded, failure_event
from ..common.reporting import report
from ..common.settings import settings
from .verification import verify_reports  # Compatibility export for existing callers.


def reclaim_guidance():
    return files("unlockops.reclaim").joinpath("reclaim-report-guide.md").read_text(encoding="utf-8")


def build_report_payload(targets, *, scan_complete, error_code=None, display_facts=None):
    """Build S-04-shaped data without modifying the validated server decisions.

    ``display_facts`` is optional, assignment-keyed factual metadata. Missing user
    names remain null. ``observed_at`` is never interpreted as a last-use date.
    A successful Agent scan is still EXECUTING until Spring stores and delivers it.
    """
    candidates, needs_review, seen = [], [], set()
    metadata = display_facts or {}
    if not isinstance(metadata, Mapping):
        raise ValueError("Display facts must be keyed by assignment id")
    for original in targets:
        row = ReclaimCandidate.model_validate(original).model_dump(mode="json")
        if row["assignment_id"] in seen:
            raise ValueError("A report cannot contain the same assignment twice")
        seen.add(row["assignment_id"])
        supplied = metadata.get(row["assignment_id"], {})
        facts = supplied if isinstance(supplied, Mapping) else {}
        name = facts.get("user_name")
        name = name.strip() if isinstance(name, str) and name.strip() else None
        if row["review_required"]:
            # Only explicitly supplied missing facts or facts proven by the wire
            # row can be described. Do not guess which date is unavailable.
            explicit = facts.get("missing")
            missing = list(dict.fromkeys(x.strip() for x in explicit if isinstance(x, str) and x.strip())) if isinstance(explicit, list) else []
            if row["cost_impact"]["status"] == "UNKNOWN" and "비용 근거" not in missing:
                missing.append("비용 근거")
            if not missing:
                missing.append("회수 판정에 필요한 정보")
            needs_review.append({
                "assignment_id": row["assignment_id"], "user_name": name,
                "platform": row["platform"], "missing": missing,
            })
        elif row["candidate_status"] == "PENDING_REVIEW":
            # Older notified candidates remain visible; notification deduplication
            # and final candidate/episode identity belong to Spring.
            candidate = deepcopy(row)
            candidate["user_name"] = name
            candidate["resource_name"] = facts.get("resource_name") if isinstance(facts.get("resource_name"), str) else None
            candidate["last_used_at"] = facts.get("last_used_at") if isinstance(facts.get("last_used_at"), str) else None
            candidates.append(candidate)
    failed = not scan_complete or error_code is not None
    return {
        "task_type": "RECLAIM_SCAN",
        "status": "FAILED" if failed else "EXECUTING",
        "reason_code": "SCAN_FAILED" if failed else "SCAN_IN_PROGRESS",
        "scan_complete": not failed,
        "summary": {"needs_review_count": len(needs_review), "candidate_count": len(candidates)},
        "needs_review": needs_review,
        "candidates": candidates,
    }


def build_failure_event(job, state, code, *, max_bytes):
    """Keep a bounded prefix of checked rows on every Agent failure path.

    No unchecked or rewritten row is used as a partial fact. The result count is
    recomputed after bounding so it always describes the rows actually returned.
    """
    event = failure_event(job, code)
    context = state.get("context") or {}
    if context.get("snapshot_id") and context.get("as_of"):
        event["result"].update(snapshot_id=context["snapshot_id"], as_of=context["as_of"])
    event["result"]["message"] = "일부만 조회되었거나 점검을 완료하지 못했습니다. 부분 결과는 알림 대상이 아닙니다."
    rows = state.get("before_report_targets", state.get("targets", []))

    def selected(count):
        event["targets"] = rows[:count] if context.get("snapshot_id") else []
        event["result"]["needs_review_count"] = sum(row["review_required"] for row in event["targets"])
        return len(json.dumps(event, ensure_ascii=False).encode()) <= max_bytes

    low, high = 0, len(rows)
    while low < high:
        mid = (low + high + 1) // 2
        if selected(mid):
            low = mid
        else:
            high = mid - 1
    selected(low)
    return ReclaimEvent.model_validate(event).model_dump(mode="json")


def report_from_event(event, *, display_facts=None):
    """Expose the agreed Agent report, keeping the legacy server event separate."""
    checked = ReclaimEvent.model_validate(event).model_dump(mode="json")
    result = checked["result"]
    payload = build_report_payload(
        checked["targets"], scan_complete=result["scan_complete"],
        error_code=result["reason_code"] if result["status"] == "FAILED" else None,
        display_facts=display_facts,
    )
    payload.update({key: result[key] for key in ("run_id", "snapshot_id", "as_of", "message")})
    return payload

@guarded
async def compose_reports(state):
    targets = []
    baseline = deepcopy(state["targets"])
    notified = {row['assignment_id'] for row in state.get('history', [])
                if row['candidate_status'] == 'PENDING_REVIEW' and row.get('notified_at')}
    generated = 0
    for original in baseline:
        item = deepcopy(original)
        if (item['candidate_status'] == 'PENDING_REVIEW' and not item['review_required']
                and not item.get('notified_at') and item['assignment_id'] not in notified
                and generated < settings.max_model_steps // 2):
            generated += 1
            facts = {k: deepcopy(item[k]) for k in ("platform", "candidate_status", "candidate_reason_code", "exclusion_reason_code", "review_required", "cost_impact", "action_taken")}
            try:
                text, mode = await report(facts, deepcopy(state["policy_evidence"]), item["explanation"], guidance=reclaim_guidance())
                if isinstance(text, str) and 0 < len(text.strip()) <= 2000 and mode in {"llm", "template"}:
                    item.update(explanation=text.strip(), generation_mode=mode)
            except Exception:
                # Optional narration cannot turn checked facts into a failed scan.
                pass
        targets.append(ReclaimCandidate.model_validate(item).model_dump(mode="json"))
    return {"targets": targets, "before_report_targets": baseline}
