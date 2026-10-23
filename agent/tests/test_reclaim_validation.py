"""Reclaim validation failures must preserve only checked rows and never narrate them."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest

from unlockops.common import runtime
from unlockops.common.models import ToolFailure
from unlockops.common.settings import settings
from unlockops.reclaim import graph, reporting, verification

from test_reclaim_agent_design import (
    CATALOG, SnapshotTools, candidate, forbid_narration, invoke, needs_review,
)


class FaultTools(SnapshotTools):
    def __init__(self, pages, fault):
        super().__init__(pages)
        self.fault = fault

    async def call(self, name, args):
        response = await super().call(name, args)
        self.fault(name, args, response)
        return response


@pytest.mark.parametrize("fault", ["content", "hash", "run"])
async def test_invalid_frozen_context_stops_before_policy_or_scan(monkeypatch, fault):
    forbid_narration(monkeypatch)

    def mutate(name, args, response):
        if name != "get_reclaim_check_context":
            return
        if fault == "content":
            response["context"]["policy"]["content"] += "\nUnverified rule"
        elif fault == "hash":
            response["context"]["policy_hash"] = "0" * 64
        else:
            response["run_id"] = str(uuid4())

    tools = FaultTools([[candidate()]], mutate)
    state = await invoke(tools)
    assert state["result_event"]["result"]["reason_code"] == "SCAN_FAILED"
    assert state["report_payload"]["candidates"] == []
    assert tools.calls == ["get_reclaim_check_context"]


async def test_superseded_job_skips_all_scanning_and_reporting(monkeypatch):
    forbid_narration(monkeypatch)

    def stale_job(name, args, response):
        if name == "get_reclaim_check_context":
            response["job_event_id"] = str(uuid4())

    tools = FaultTools([[candidate()]], stale_job)
    state = await invoke(tools)
    assert state["result_event"] == {}
    assert "report_payload" not in state
    assert tools.calls == ["get_reclaim_check_context"]


@pytest.mark.parametrize("field,value", [
    ("run_id", str(uuid4())),
    ("snapshot_id", str(uuid4())),
    ("as_of", "2099-01-01T09:00:00+09:00"),
    ("expected_count", 999),
    ("next_cursor", ""),
    ("next_cursor", " " * 3),
    ("next_cursor", "x" * 501),
    ("next_cursor", "1"),  # Second page returning its own cursor.
])
async def test_invalid_second_page_metadata_keeps_only_previous_page(monkeypatch, field, value):
    forbid_narration(monkeypatch)
    checked = candidate()

    def mutate(name, args, response):
        if name == "list_revocation_candidates" and args["cursor"] == "1":
            response[field] = value

    tools = FaultTools([[checked], [needs_review()]], mutate)
    state = await invoke(tools)
    assert state["result_event"]["result"]["reason_code"] == "SCAN_FAILED"
    assert state["result_event"]["targets"] == [checked]
    assert state["report_payload"]["summary"] == {"candidate_count": 1, "needs_review_count": 0}
    assert "get_reclaim_notification_history" not in tools.calls


async def test_overfull_page_is_not_retained_as_checked_partial_result(monkeypatch):
    forbid_narration(monkeypatch)
    checked = needs_review()

    def overflow(name, args, response):
        if name == "list_revocation_candidates" and args["cursor"] == "1":
            response["items"].append(candidate(assignment_id=str(uuid4())))

    tools = FaultTools([[checked], [candidate()]], overflow)
    state = await invoke(tools)
    assert state["error"]["code"] == "SCAN_LIMIT"
    assert state["result_event"]["targets"] == [checked]
    assert state["report_payload"]["summary"]["needs_review_count"] == 1
    assert state["report_payload"]["candidates"] == []


@pytest.mark.parametrize("fault", ["record", "future", "stale_snapshot", "blank_source", "cost", "clause"])
async def test_wrong_fact_or_missing_confirmation_evidence_never_becomes_a_candidate(monkeypatch, fault):
    forbid_narration(monkeypatch)
    checked = needs_review()
    untrusted = candidate()
    fact = untrusted["fact_evidence"][0]
    if fault == "record":
        fact["record_id"] = str(uuid4())
    elif fault == "future":
        fact["observed_at"] = "2099-01-01T09:00:00+09:00"
    elif fault == "stale_snapshot":
        fact.update(source="reclaim_snapshot_items", observed_at="2020-01-01T09:00:00+09:00")
    elif fault == "blank_source":
        fact["source"] = " "
    elif fault == "cost":
        untrusted["cost_impact"] = {"status": "UNKNOWN"}
    else:
        from test_workflows import policy_reply
        untrusted["policy_evidence"] = [
            e for e in policy_reply()["evidence"] if e["article"].startswith("POL-06 제2조")
        ]
        assert untrusted["policy_evidence"]

    state = await invoke(SnapshotTools([[checked], [untrusted]]))
    assert state["result_event"]["result"]["reason_code"] == "SCAN_FAILED"
    assert state["result_event"]["targets"] == [checked]
    assert state["report_payload"]["summary"]["needs_review_count"] == 1
    assert state["report_payload"]["candidates"] == []


async def test_live_snapshot_fact_evidence_is_accepted(monkeypatch):
    forbid_narration(monkeypatch)
    row = needs_review()
    row["fact_evidence"][0].update(source="reclaim_snapshot_items", observed_at=CATALOG["as_of"])
    state = await invoke(SnapshotTools([[row]]))
    assert state["result_event"]["result"]["scan_complete"] is True
    assert state["report_payload"]["summary"]["needs_review_count"] == 1


async def test_mixed_scan_preserves_human_retention_and_employee_left_decisions(monkeypatch):
    idle = candidate()
    left = candidate(assignment_id=str(uuid4()), candidate_reason_code="EMPLOYEE_LEFT")
    retained = candidate(assignment_id=str(uuid4()), candidate_status="RETAINED", exclusion_reason_code="RETENTION_APPROVED")
    excluded = candidate(assignment_id=str(uuid4()), candidate_status="EXCLUDED", exclusion_reason_code="ACTIVE_OTHER_TF")
    unknown = needs_review()
    rows = [idle, left, retained, excluded, unknown]
    narrated_reasons = []

    async def narrate(facts, evidence, template):
        narrated_reasons.append(facts["candidate_reason_code"])
        return "확인된 근거에 따라 담당자의 회수 검토가 필요합니다.", "llm"

    monkeypatch.setattr(reporting, "report", narrate)
    state = await invoke(SnapshotTools([rows]))
    assert state["verified_targets"] == rows
    assert state["result_event"]["result"]["status"] == "EXECUTING"
    assert state["result_event"]["result"]["scan_complete"] is True
    payload = state["report_payload"]
    assert payload["summary"] == {"candidate_count": 2, "needs_review_count": 1}
    assert [r["candidate_reason_code"] for r in payload["candidates"]] == ["TF_ENDED_UNUSED_30D", "EMPLOYEE_LEFT"]
    assert narrated_reasons == ["TF_ENDED_UNUSED_30D", "EMPLOYEE_LEFT"]
    assert state["result_event"]["targets"][2:] == rows[2:]
    assert all(r["action_taken"] == "NONE" for r in state["result_event"]["targets"])


async def test_empty_scan_finishes_without_history_calls_or_narration(monkeypatch):
    forbid_narration(monkeypatch)
    tools = SnapshotTools([[]])
    state = await invoke(tools)
    assert state["result_event"]["result"]["status"] == "EXECUTING"
    assert state["result_event"]["result"]["scan_complete"] is True
    assert state["report_payload"]["summary"] == {"candidate_count": 0, "needs_review_count": 0}
    assert "get_reclaim_notification_history" not in tools.calls


async def test_invalid_row_on_same_page_keeps_only_verified_prefix(monkeypatch):
    forbid_narration(monkeypatch)
    checked, untrusted = needs_review(), candidate()
    untrusted["fact_evidence"][0]["record_id"] = str(uuid4())
    state = await invoke(SnapshotTools([[checked, untrusted]]))
    assert state["error"]["code"] == "FACT_SCOPE"
    assert state["result_event"]["targets"] == [checked]
    assert state["report_payload"]["summary"]["needs_review_count"] == 1


async def test_invalid_page_schema_cannot_discard_a_previous_checked_page(monkeypatch):
    forbid_narration(monkeypatch)
    checked = candidate()

    def bad_schema(name, args, response):
        if name == "list_revocation_candidates" and args["cursor"] == "1":
            response["items"][0]["action_taken"] = "REVOKED"

    tools = FaultTools([[checked], [needs_review()]], bad_schema)
    state = await invoke(tools)
    assert state["error"]["code"] == "INVALID_TOOL_OUTPUT"
    assert state["result_event"]["targets"] == [checked]
    assert state["report_payload"]["summary"]["candidate_count"] == 1


@pytest.mark.parametrize("fault", ["unrelated", "duplicate", "unavailable"])
async def test_bad_notification_history_preserves_full_checked_scan_without_narration(monkeypatch, fault):
    forbid_narration(monkeypatch)
    checked, unknown = candidate(), needs_review()

    class HistoryTools(SnapshotTools):
        async def call(self, name, args):
            response = await super().call(name, args)
            if name == "get_reclaim_notification_history":
                if fault == "unavailable":
                    raise ToolFailure("MCP_UNAVAILABLE", "History unavailable")
                row = {
                    "assignment_id": str(uuid4()) if fault == "unrelated" else checked["assignment_id"],
                    "target_id": str(uuid4()), "episode_id": str(uuid4()),
                    "candidate_status": "PENDING_REVIEW", "notified_at": None, "notifications": [],
                }
                response["items"] = [row] if fault == "unrelated" else [row, deepcopy(row)]
            return response

    state = await invoke(HistoryTools([[checked, unknown]]))
    assert state["result_event"]["result"]["reason_code"] == "SCAN_FAILED"
    assert state["result_event"]["targets"] == [checked, unknown]
    assert state["report_payload"]["summary"] == {"candidate_count": 1, "needs_review_count": 1}


@pytest.mark.parametrize("recovers", [True, False])
async def test_candidate_mcp_retry_recovers_or_preserves_checked_page(monkeypatch, recovers):
    forbid_narration(monkeypatch)
    monkeypatch.setattr(runtime, "settings", replace(settings, max_execution_attempts=3))
    delays = []

    async def no_wait(delay):
        delays.append(delay)

    monkeypatch.setattr(runtime.asyncio, "sleep", no_wait)

    class RetryTools(SnapshotTools):
        attempts = 0

        async def call(self, name, args):
            if name == "list_revocation_candidates" and args["cursor"] == "1":
                self.attempts += 1
                if not recovers or self.attempts < 3:
                    raise ToolFailure("MCP_UNAVAILABLE", "Temporary page failure", retryable=True)
            return await super().call(name, args)

    rows = [needs_review(), needs_review()]
    tools = RetryTools([[rows[0]], [rows[1]]])
    state = await invoke(tools)
    assert tools.attempts == 3
    assert delays == [1, 2]
    assert state["result_event"]["targets"] == (rows if recovers else rows[:1])
    assert state["result_event"]["result"]["status"] == ("EXECUTING" if recovers else "FAILED")
    assert state["report_payload"]["summary"]["needs_review_count"] == (2 if recovers else 1)


@pytest.mark.parametrize("fault", ["count", "decision", "baseline", "crash"])
async def test_report_writer_failure_restores_original_scan_checkpoint(monkeypatch, fault):
    checked, unknown = candidate(), needs_review()

    async def bad_writer(state):
        changed = deepcopy(state["targets"])
        if fault == "count":
            changed.pop()
        else:
            changed[0]["cost_impact"]["monthly_amount"] = "0.00"
        if fault == "crash":
            raise RuntimeError("Report writer crashed")
        result = {"targets": changed}
        if fault == "baseline":
            # Even rewriting the writer-owned comparison input cannot approve a changed fact.
            result["before_report_targets"] = deepcopy(changed)
        return result

    monkeypatch.setattr(graph, "compose_reports", bad_writer)
    from langgraph.checkpoint.memory import InMemorySaver
    from unlockops_worker.runtime import run_job, read_reclaim_report

    tools, saver = SnapshotTools([[checked, unknown]]), InMemorySaver()
    event = await run_job(tools.job, saver, tools)
    assert event["result"]["reason_code"] == "SCAN_FAILED"
    assert event["targets"] == [checked, unknown]
    payload = await read_reclaim_report(tools.job, saver)
    assert payload["summary"] == {"candidate_count": 1, "needs_review_count": 1}
    assert payload["candidates"][0]["cost_impact"]["monthly_amount"] == "19.00"
    calls = list(tools.calls)
    assert await run_job(tools.job, saver, tools) == event
    assert tools.calls == calls


@pytest.mark.parametrize("row", [
    needs_review(),
    candidate(candidate_status="EXCLUDED", exclusion_reason_code="ACTIVE_OTHER_TF"),
    candidate(candidate_status="RETAINED", exclusion_reason_code="RETENTION_APPROVED"),
    candidate(target_id=str(uuid4()), episode_id=str(uuid4()), notified_at=CATALOG["as_of"]),
])
async def test_narration_cannot_rewrite_review_excluded_retained_or_notified_rows(row):
    changed = {**deepcopy(row), "explanation": "새로 작성한 설명입니다.", "generation_mode": "llm"}
    result = await verification.verify_reports({"verified_targets": [row], "targets": [changed]})
    assert result["error"]["code"] == "REPORT_FACT_MISMATCH"


@pytest.mark.parametrize("text", [" ", "x" * 2001])
async def test_verifier_rejects_blank_or_oversized_changed_explanation(text):
    original = candidate()
    changed = {**deepcopy(original), "explanation": text}
    result = await verification.verify_reports({"verified_targets": [original], "targets": [changed]})
    assert result["error"]["code"] == "REPORT_FACT_MISMATCH"


@pytest.mark.parametrize("scan_complete,count", [(False, 1), (True, 2)])
def test_finish_cannot_claim_a_complete_scan_without_all_checked_rows(scan_complete, count):
    row = candidate()
    tools = SnapshotTools([[row]])
    state = {
        "job": tools.job.model_dump(mode="json"), "targets": [row], "verified_targets": [row],
        "scan_complete": scan_complete,
        "context": {"snapshot_id": tools.snapshot, "as_of": CATALOG["as_of"], "expected_count": count},
    }
    result = graph.finish(state)
    assert result["result_event"]["result"]["reason_code"] == "SCAN_FAILED"
    assert result["result_event"]["targets"] == [row]
    assert result["report_payload"]["summary"]["candidate_count"] == 1
