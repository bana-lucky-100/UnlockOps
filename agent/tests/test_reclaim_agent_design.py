"""Reclaim design boundaries: partial evidence, separate review rows and immutable decisions."""
from copy import deepcopy
from uuid import uuid4

import pytest

from unlockops.common.models import ToolFailure
from unlockops.common.workflow_contracts import ReclaimJob
from unlockops.reclaim import graph, reporting, policy as reclaim_policy

# These fixtures are the same frozen policy/contract rows used by the existing v4 flow tests.
from test_workflows import CANDIDATE, CATALOG, policy, policy_reply


def candidate(**changes):
    return {**deepcopy(CANDIDATE), **changes}


def needs_review(**changes):
    return candidate(
        assignment_id=str(uuid4()), candidate_status=None, candidate_reason_code=None,
        review_required=True, cost_impact={"status": "UNKNOWN"}, **changes,
    )


class SnapshotTools:
    """Only the read tools available to the reclaim graph; every page is deterministic."""

    def __init__(self, pages, *, fail_page=None, bad_policy=False):
        self.job = ReclaimJob(
            schema_version=2, event_id=uuid4(), run_id=uuid4(), trigger="MANUAL_DEMO",
            scope_key="company-a-copilot", scheduled_for=CATALOG["as_of"],
        )
        self.snapshot = str(uuid4())
        self.pages, self.fail_page, self.bad_policy = pages, fail_page, bad_policy
        self.calls = []

    async def call(self, name, args):
        self.calls.append(name)
        if name == "get_reclaim_check_context":
            source = policy()
            return {
                "schema_version": 2, "run_id": str(self.job.run_id),
                "job_event_id": str(self.job.event_id), "snapshot_id": self.snapshot,
                "as_of": CATALOG["as_of"], "expected_count": sum(map(len, self.pages)),
                "context": {"policy": source, "policy_hash": source["source_hash"], "rules": []},
            }
        if name in {"search_workflow_policy", "read_workflow_policy"}:
            response = deepcopy(policy_reply())
            if self.bad_policy:
                response["evidence"][0]["text"] = "이 문장은 고정된 사내 규정에 없습니다."
            return response
        if name == "list_revocation_candidates":
            page = 0 if args["cursor"] is None else int(args["cursor"])
            if page == self.fail_page:
                raise ToolFailure("MCP_UNAVAILABLE", "Read unavailable", retryable=False)
            return {
                "run_id": str(self.job.run_id), "snapshot_id": self.snapshot,
                "as_of": CATALOG["as_of"], "expected_count": sum(map(len, self.pages)),
                "next_cursor": str(page + 1) if page + 1 < len(self.pages) else None,
                "items": deepcopy(self.pages[page]),
            }
        if name == "get_reclaim_notification_history":
            return {"items": []}
        pytest.fail(f"Reclaim must not call another tool: {name}")


async def invoke(tools):
    return await graph.build_graph(tools, tools.job).ainvoke(
        {"job": tools.job.model_dump(mode="json")}, {"recursion_limit": 40},
    )


def forbid_narration(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("This branch must not spend model calls or narrate unconfirmed facts")
    monkeypatch.setattr(reporting, "report", forbidden)


def test_report_payload_separates_confirmed_candidates_and_additional_review():
    from unlockops.reclaim.reporting import build_report_payload
    pending = candidate()
    delivered = candidate(
        assignment_id=str(uuid4()), target_id=str(uuid4()), episode_id=str(uuid4()),
        notified_at=CATALOG["as_of"], skip_reason_code="ALREADY_NOTIFIED",
    )
    excluded = candidate(
        assignment_id=str(uuid4()), candidate_status="EXCLUDED",
        exclusion_reason_code="ACTIVE_OTHER_TF",
    )
    retained = candidate(
        assignment_id=str(uuid4()), candidate_status="RETAINED",
        exclusion_reason_code="RETENTION_APPROVED",
    )
    unknown = needs_review()
    original = deepcopy([pending, delivered, excluded, retained, unknown])
    payload = build_report_payload(original, scan_complete=True)

    assert payload["task_type"] == "RECLAIM_SCAN"
    assert (payload["status"], payload["reason_code"]) == ("EXECUTING", "SCAN_IN_PROGRESS")
    assert {row["assignment_id"] for row in payload["candidates"]} == {
        pending["assignment_id"], delivered["assignment_id"],
    }
    assert payload["summary"]["candidate_count"] == 2
    assert payload["summary"]["needs_review_count"] == len(payload["needs_review"]) == 1
    assert payload["needs_review"][0]["assignment_id"] == unknown["assignment_id"]
    assert payload["needs_review"][0]["user_name"] is None
    assert payload["needs_review"][0]["platform"] == "GITHUB"
    assert "비용 근거" in payload["needs_review"][0]["missing"]
    # Usage evidence observation time is not the employee's last activity time.
    assert payload["candidates"][0]["last_used_at"] is None
    assert payload["candidates"][0]["user_name"] is None
    assert original == [pending, delivered, excluded, retained, unknown]


def test_report_payload_uses_only_supplied_display_facts_and_human_missing_labels():
    from unlockops.reclaim.reporting import build_report_payload
    unknown = needs_review()
    facts = {unknown["assignment_id"]: {
        "user_name": "김지성", "resource_name": "Copilot",
        "missing": ["마지막 사용일", "TF 종료일"],
    }}
    payload = build_report_payload([unknown], scan_complete=True, display_facts=facts)
    row = payload["needs_review"][0]
    assert row["user_name"] == "김지성"
    assert row["platform"] == "GITHUB"
    assert "마지막 사용일" in row["missing"] and "TF 종료일" in row["missing"]
    assert all(value.strip() for value in row["missing"])
    assert not {"USAGE_OBSERVATION", "RECLAIM_FACTS", "PRICE_EVIDENCE"} & set(row["missing"])
    assert payload["candidates"] == []


def test_report_payload_partial_failure_preserves_confirmed_rows_and_review_count():
    from unlockops.reclaim.reporting import build_report_payload
    checked, unknown = candidate(), needs_review()
    payload = build_report_payload(
        [checked, unknown], scan_complete=False, error_code="MCP_UNAVAILABLE",
    )
    assert (payload["status"], payload["reason_code"]) == ("FAILED", "SCAN_FAILED")
    assert payload["scan_complete"] is False
    assert [row["assignment_id"] for row in payload["candidates"]] == [checked["assignment_id"]]
    assert payload["summary"]["needs_review_count"] == len(payload["needs_review"]) == 1


async def test_page_two_failure_retains_checked_candidate_without_history_or_llm(monkeypatch):
    forbid_narration(monkeypatch)
    checked = candidate()
    tools = SnapshotTools([[checked], [candidate(assignment_id=str(uuid4()))]], fail_page=1)
    state = await invoke(tools)

    event = state["result_event"]
    assert (event["result"]["status"], event["result"]["reason_code"]) == ("FAILED", "SCAN_FAILED")
    assert event["result"]["scan_complete"] is False
    assert event["targets"] == [checked]
    reported = state["report_payload"]["candidates"]
    assert len(reported) == 1 and all(reported[0][key] == value for key, value in checked.items())
    assert "get_reclaim_notification_history" not in tools.calls
    assert not {"execute_access_plan", "grant_permission"} & set(tools.calls)


async def test_information_shortage_only_does_not_invoke_llm_or_claim_done(monkeypatch):
    forbid_narration(monkeypatch)
    unknown = needs_review()
    state = await invoke(SnapshotTools([[unknown]]))

    assert state["result_event"]["result"]["status"] == "EXECUTING"
    assert state["result_event"]["result"]["needs_review_count"] == 1
    assert state["report_payload"]["candidates"] == []
    assert state["report_payload"]["summary"]["needs_review_count"] == 1
    assert state["report_payload"]["needs_review"][0]["user_name"] is None
    assert state["result_event"]["targets"][0]["review_required"] is True


async def test_partial_review_count_matches_preserved_rows(monkeypatch):
    forbid_narration(monkeypatch)
    unknown = needs_review()
    state = await invoke(SnapshotTools([[unknown], [candidate()]], fail_page=1))
    assert state["result_event"]["result"]["status"] == "FAILED"
    assert state["result_event"]["result"]["needs_review_count"] == 1
    assert state["report_payload"]["summary"]["needs_review_count"] == 1
    assert len(state["report_payload"]["needs_review"]) == 1


async def test_tampered_rag_quote_fails_before_candidate_scan_or_llm(monkeypatch):
    forbid_narration(monkeypatch)
    tools = SnapshotTools([[candidate()]], bad_policy=True)
    state = await invoke(tools)

    assert state["result_event"]["result"]["status"] == "FAILED"
    assert state["result_event"]["result"]["reason_code"] == "SCAN_FAILED"
    assert "list_revocation_candidates" not in tools.calls
    assert "get_reclaim_notification_history" not in tools.calls
    assert state["report_payload"]["candidates"] == []


async def test_unverified_second_page_is_never_retained_as_partial_candidate(monkeypatch):
    forbid_narration(monkeypatch)
    checked = candidate()
    forged = candidate(assignment_id=str(uuid4()))
    forged["policy_evidence"][0]["source_hash"] = "0" * 64
    tools = SnapshotTools([[checked], [forged]])
    state = await invoke(tools)

    assert state["result_event"]["result"]["status"] == "FAILED"
    assert state["result_event"]["targets"] == [checked]
    reported = state["report_payload"]["candidates"]
    assert len(reported) == 1 and all(reported[0][key] == value for key, value in checked.items())
    assert "get_reclaim_notification_history" not in tools.calls


@pytest.mark.parametrize("field,value", [
    ("assignment_id", str(uuid4())),
    ("platform", "JIRA"),
    ("candidate_reason_code", "EMPLOYEE_LEFT"),
    ("cost_impact", {"status": "ESTIMATED", "monthly_amount": "0.00", "currency": "USD", "basis": "SYNTHETIC_CONTRACT"}),
    ("policy_evidence", []),
    ("fact_evidence", []),
])
async def test_verification_rejects_identity_decision_cost_or_evidence_mutation(field, value):
    original = candidate()
    changed = deepcopy(original)
    changed[field] = value
    result = await reporting.verify_reports({
        "before_report_targets": [original], "targets": [changed],
    })
    assert result.get("error"), f"Narration must not change the frozen {field}"


async def test_composition_and_verification_allow_only_explanation_and_generation_mode(monkeypatch):
    original = candidate()
    async def narrative(facts, evidence, template, *, guidance=""):
        return "확인된 규정과 사용 기록에 따라 담당자의 회수 검토가 필요합니다.", "llm"
    monkeypatch.setattr(reporting, "report", narrative)
    state = {
        "targets": [deepcopy(original)], "history": [],
        "policy_evidence": policy_reply()["evidence"], "scan_complete": True,
    }
    composed = await reporting.compose_reports(state)
    assert not composed.get("error")
    state.update(composed)
    state.setdefault("before_report_targets", [original])
    verified = await reporting.verify_reports(state)
    assert not verified.get("error")
    final = state["targets"][0]
    assert final["generation_mode"] == "llm"
    assert final["explanation"] != original["explanation"]
    assert {k: v for k, v in final.items() if k not in {"explanation", "generation_mode"}} == {
        k: v for k, v in original.items() if k not in {"explanation", "generation_mode"}
    }


def test_reclaim_guidance_is_packaged_text():
    assert reporting.reclaim_guidance().strip()


async def test_composition_passes_reclaim_guidance_to_report(monkeypatch):
    received = []
    async def narrative(facts, evidence, template, *, guidance=""):
        received.append(guidance)
        return template, "template"
    monkeypatch.setattr(reporting, "report", narrative)
    await reporting.compose_reports({"targets": [candidate()], "history": [], "policy_evidence": policy_reply()["evidence"]})
    assert received == [reporting.reclaim_guidance()]


async def test_report_api_replays_without_model_calls_or_changing_server_wire(monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    from unlockops.common.workflow_contracts import ReclaimEvent
    from unlockops_worker.runtime import run_reclaim_report, read_reclaim_report, run_job

    calls = []
    async def narrate(facts, evidence, template, *, guidance=""):
        calls.append(facts)
        return template, "template"
    monkeypatch.setattr(reporting, "report", narrate)
    checked, unknown = candidate(), needs_review()
    tools, saver = SnapshotTools([[checked, unknown]]), InMemorySaver()
    assert await read_reclaim_report(tools.job, saver) is None
    metadata = {unknown["assignment_id"]: {"user_name": "김지성", "missing": ["마지막 사용일", "TF 종료일"]}}
    payload = await run_reclaim_report(tools.job, saver, tools, display_facts=metadata)
    assert payload["summary"]["needs_review_count"] == 1
    assert payload["needs_review"][0]["user_name"] == "김지성"
    assert payload["needs_review"][0]["platform"] == "GITHUB"
    assert "TF 종료일" in payload["needs_review"][0]["missing"]
    assert payload["run_id"] == str(tools.job.run_id)
    previous = list(tools.calls), len(calls)
    assert await read_reclaim_report(tools.job, saver, display_facts=metadata) == payload
    wire = await run_job(tools.job, saver, tools)
    ReclaimEvent.model_validate(wire)
    assert "candidates" not in wire and "report_payload" not in wire
    assert "user_name" not in wire["targets"][0]
    assert previous == (tools.calls, len(calls))
    with pytest.raises(ValueError, match="Checkpoint belongs"):
        await read_reclaim_report(tools.job.model_copy(update={"scope_key": "another-scope"}), saver)


def test_failed_payload_bounds_rows_without_losing_all_checked_results():
    import json
    from unlockops.reclaim.reporting import build_failure_event, report_from_event
    first = needs_review(explanation="확인된 부분 결과입니다. " * 300)
    second = candidate(assignment_id=str(uuid4()), explanation="확인된 부분 결과입니다. " * 300)
    tools = SnapshotTools([[first, second]])
    state = {"context": {"snapshot_id": tools.snapshot, "as_of": CATALOG["as_of"]},
             "targets": [first, second]}
    event = build_failure_event(tools.job, state, "SCAN_LIMIT", max_bytes=18000)
    assert len(json.dumps(event, ensure_ascii=False).encode()) <= 18000
    assert len(event["targets"]) == 1
    assert event["result"]["snapshot_id"] == tools.snapshot
    assert event["result"]["needs_review_count"] == 1
    assert report_from_event(event)["summary"]["needs_review_count"] == 1


async def test_candidate_citation_must_name_the_section_containing_its_quote(monkeypatch):
    forbid_narration(monkeypatch)
    forged = candidate()
    forged["policy_evidence"][0]["article"] = "POL-06 제1조"
    state = await invoke(SnapshotTools([[forged]]))
    assert state["result_event"]["result"]["status"] == "FAILED"
    assert state["result_event"]["targets"] == []


async def test_missing_mandatory_reclaim_clause_stops_before_scan(monkeypatch):
    forbid_narration(monkeypatch)
    class MissingClauseTools(SnapshotTools):
        async def call(self, name, args):
            response = await super().call(name, args)
            if name == "read_workflow_policy":
                response["evidence"] = [e for e in response["evidence"] if not reclaim_policy._is_reclaim_clause(e["article"])]
            return response
    tools = MissingClauseTools([[candidate()]])
    state = await invoke(tools)
    assert state["result_event"]["result"]["status"] == "FAILED"
    assert "list_revocation_candidates" not in tools.calls


@pytest.mark.parametrize("text,mode", [("", "llm"), ("x" * 2001, "llm"), ("valid", "unverified")])
async def test_bad_narration_keeps_checked_template_instead_of_failing_scan(monkeypatch, text, mode):
    original = candidate()
    async def invalid(*args, guidance=""):
        return text, mode
    monkeypatch.setattr(reporting, "report", invalid)
    result = await reporting.compose_reports({
        "targets": [original], "history": [], "policy_evidence": policy_reply()["evidence"],
    })
    assert not result.get("error")
    assert result["targets"] == [original]


async def test_report_callback_cannot_mutate_frozen_nested_facts_or_citations(monkeypatch):
    original = candidate()
    evidence = policy_reply()["evidence"]
    evidence_before = deepcopy(evidence)
    async def mutate_arguments(facts, sources, template, *, guidance=""):
        facts["cost_impact"]["monthly_amount"] = "0.00"
        sources[0]["text"] = "Untrusted replacement"
        return template, "template"
    monkeypatch.setattr(reporting, "report", mutate_arguments)
    result = await reporting.compose_reports({"targets": [original], "history": [], "policy_evidence": evidence})
    assert result["targets"] == [original]
    assert evidence == evidence_before


async def test_reclaim_redelivery_reuses_durable_result_without_another_scan(monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    from unlockops_worker.runtime import run_job
    calls = []
    async def narrative(facts, evidence, template, *, guidance=""):
        calls.append(facts)
        return template, "template"
    monkeypatch.setattr(reporting, "report", narrative)
    tools, saver = SnapshotTools([[candidate()]]), InMemorySaver()
    first = await run_job(tools.job, saver, tools)
    first_calls = list(tools.calls)
    assert first["event_type"] == "RECLAIM_CHECKED"
    assert len(calls) == 1
    assert await run_job(tools.job, saver, tools) == first
    assert tools.calls == first_calls
    assert len(calls) == 1


async def test_worker_owns_mcp_cancel_scope_and_replay_does_not_reopen(monkeypatch):
    """Real AnyIO task ownership catches the Docker-only MCP teardown failure."""
    import asyncio
    import anyio
    from langgraph.checkpoint.memory import InMemorySaver
    from unlockops_worker import runtime as worker

    tools = SnapshotTools([[needs_review()]])
    owner = asyncio.current_task()
    lifetime = []

    class TaskBoundMCP:
        async def __aenter__(self):
            lifetime.append(("open", asyncio.current_task()))
            self.scope = anyio.CancelScope()
            self.scope.__enter__()
            return self

        async def __aexit__(self, *args):
            lifetime.append(("close", asyncio.current_task()))
            self.scope.__exit__(*args)

        async def call(self, name, arguments):
            return await tools.call(name, arguments)

    monkeypatch.setattr(worker, "MCPTools", TaskBoundMCP)
    saver = InMemorySaver()
    first = await worker.run_job(tools.job, saver)
    assert first["event_type"] == "RECLAIM_CHECKED"
    assert first["result"]["scan_complete"] is True
    assert lifetime == [("open", owner), ("close", owner)]
    calls = list(tools.calls)
    assert await worker.run_job(tools.job, saver) == first
    assert tools.calls == calls
    assert lifetime == [("open", owner), ("close", owner)]
