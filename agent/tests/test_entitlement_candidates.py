"""실제 후보만 선택하고, 해당 없음·범위 밖·명시 권한 불일치는 추측하지 않는다."""
from copy import deepcopy
from dataclasses import replace
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from unlockops.access import graph, planner, selection
from unlockops.access.intent import interpret_v4
from unlockops.common.models import Intent, ToolFailure


EDITOR = "11111111-1111-4111-8111-111111111111"
VIEWER = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
RESOURCE = "44444444-4444-4444-8444-444444444444"


def option(identifier=EDITOR, code="EDITOR_SEAT", resource=RESOURCE):
    return {"id": identifier, "code": code, "kind": "SEAT", "resource_id": resource,
            "name": "결제 개편 시안", "external_id": "payment-design", "platform": "FIGMA"}


def context(contents="피그마 결제 화면 시안을 수정해야 해요.", options=None):
    return {"problem": {"contents": contents, "platform": "FIGMA", "resource_id": RESOURCE,
                        "requested_entitlement_id": None},
            "entitlements": [option()] if options is None else options}


def fake_model(monkeypatch, result, calls):
    """진짜 모델 대신 전달된 스키마를 사용해 고정된 응답을 만든다."""
    class FakeModel:
        def with_structured_output(self, schema):
            self.schema = schema
            calls.append({"schema": schema})
            return self

        async def ainvoke(self, messages):
            calls[-1]["messages"] = messages
            return self.schema.model_validate(result)

    monkeypatch.setattr(planner, "settings", replace(planner.settings, mode="llm"))
    monkeypatch.setattr(planner, "model", FakeModel)


async def test_planner_supplies_real_codes_and_binds_selection_schema(monkeypatch):
    calls = []
    fake_model(monkeypatch, {"request_type": "ACCESS_REQUEST", "requested_role": "에디터",
        "entitlement_selection": {"entitlement_id": EDITOR}}, calls)
    descriptions = [{"doc_id": "POL-14", "text": "디자인 파일 편집에는 Full 좌석이 필요하다."}]
    intent = await interpret_v4("피그마 결제 화면 시안을 수정해야 해요.", "FIGMA", [option()], descriptions)
    payload = json.loads(calls[0]["messages"][1][1])
    assert payload["entitlement_options"] == [option()]
    assert payload["policy_context"] == descriptions
    assert intent.entitlement_selection.entitlement_id == UUID(EDITOR)
    assert await selection.select_entitlement(context(), intent.model_dump()) == (EDITOR, False)
    schema = calls[0]["schema"]
    with pytest.raises(ValidationError):
        schema.model_validate({"entitlement_selection": {"entitlement_id": OTHER}})
    with pytest.raises(ValidationError):
        schema.model_validate({})


@pytest.mark.parametrize("ids", [[EDITOR], [EDITOR, VIEWER]])
def test_schema_accepts_only_presented_ids_or_null(ids):
    schema = planner.candidate_intent_schema([option(identifier) for identifier in ids])
    for identifier in [*ids, None]:
        parsed = schema.model_validate({"entitlement_selection": {"entitlement_id": identifier}})
        assert parsed.entitlement_selection.entitlement_id == identifier
    with pytest.raises(ValidationError):
        schema.model_validate({"entitlement_selection": {"entitlement_id": OTHER}})


def test_empty_candidate_schema_accepts_only_null():
    schema = planner.candidate_intent_schema([])
    assert schema.model_validate({"entitlement_selection": {"entitlement_id": None}}).entitlement_selection.entitlement_id is None
    with pytest.raises(ValidationError):
        schema.model_validate({"entitlement_selection": {"entitlement_id": EDITOR}})


@pytest.mark.parametrize("options", [[], [option()]])
async def test_no_match_does_not_fall_back_to_a_single_option(monkeypatch, options):
    calls = []
    fake_model(monkeypatch, {"request_type": "ACCESS_REQUEST",
        "entitlement_selection": {"entitlement_id": None}}, calls)
    intent = await interpret_v4("피그마 결제 화면 시안을 수정해야 해요.", "FIGMA", options)
    def forbidden_model():
        pytest.fail("해당 없음 이후에는 다른 후보 선택을 다시 요청하지 않는다")
    monkeypatch.setattr(selection, "model", forbidden_model)
    with pytest.raises(ToolFailure) as error:
        await selection.select_entitlement(context(options=options), intent.model_dump())
    assert error.value.code == "OUT_OF_SCOPE"
    assert len(calls) == 1


@pytest.mark.parametrize("selected", [OTHER, "not-an-id"])
async def test_selection_rechecks_model_id_even_if_structured_output_is_bypassed(selected):
    with pytest.raises(ToolFailure) as error:
        await selection.select_entitlement(context(), {"requested_role": "",
            "entitlement_selection": {"entitlement_id": selected}})
    assert error.value.code == "OUT_OF_SCOPE"


async def test_candidate_for_another_resource_cannot_be_selected():
    ctx = context(options=[option(), option(OTHER, resource=VIEWER)])
    assert selection.entitlement_options(ctx) == [option()]
    with pytest.raises(ToolFailure):
        await selection.select_entitlement(ctx, {"requested_role": "",
            "entitlement_selection": {"entitlement_id": OTHER}})


async def test_stored_explicit_entitlement_takes_priority_over_model_choice():
    ctx = context(options=[option(), option(VIEWER, "VIEWER")])
    ctx["problem"]["requested_entitlement_id"] = VIEWER
    assert await selection.select_entitlement(ctx, {"requested_role": "",
        "entitlement_selection": {"entitlement_id": EDITOR}}) == (VIEWER, False)
    ctx["problem"]["requested_entitlement_id"] = OTHER
    with pytest.raises(ToolFailure):
        await selection.select_entitlement(ctx, {"requested_role": "",
            "entitlement_selection": {"entitlement_id": EDITOR}})


async def test_explicit_viewer_request_cannot_be_replaced_by_editor():
    ctx = context("Figma Viewer 권한을 신청합니다.")
    with pytest.raises(ToolFailure):
        await selection.select_entitlement(ctx, {"requested_role": "에디터",
            "entitlement_selection": {"entitlement_id": EDITOR}})


async def test_explicit_viewer_role_overrides_free_form_model_role():
    ctx = context("Figma Viewer 권한을 신청합니다.", [option(), option(VIEWER, "VIEWER")])
    assert await selection.select_entitlement(ctx, {"requested_role": "에디터",
        "entitlement_selection": {"entitlement_id": VIEWER}}) == (VIEWER, False)


async def test_graph_passes_scoped_candidates_and_latest_platform_descriptions(monkeypatch):
    captured = {}
    async def interpret(contents, platform, options, descriptions):
        captured.update(contents=contents, platform=platform, options=options, descriptions=descriptions)
        return Intent(request_type="ACCESS_REQUEST", entitlement_selection={"entitlement_id": EDITOR})
    monkeypatch.setattr(graph, "interpret", interpret)
    ctx = context(options=[option(), option(OTHER, resource=VIEWER)])
    ctx["policies"] = [
        {"policy_id": "company-policy", "revision": 1, "doc_id": "old", "content": "old"},
        {"policy_id": "company-policy", "revision": 2, "doc_id": "current", "content": (
            "## POL-01 | COMMON | v1.1 | 제2조\n최소 권한을 부여한다.\n"
            "## POL-14 | FIGMA | v1.0 | 제1조\n디자인 편집에는 Full 좌석이 필요하다.\n"
            "## POL-10 | DATABRICKS | v1.0 | 제1조\n다른 플랫폼 설명.\n")},
    ]
    result = await graph.interpret_request({"context": ctx})
    assert captured["options"] == [option()]
    assert len(captured["descriptions"]) == 2
    assert {item["doc_id"] for item in captured["descriptions"]} == {"current"}
    assert "DATABRICKS" not in json.dumps(captured["descriptions"])
    assert result["intent"]["entitlement_selection"]["entitlement_id"] == EDITOR


async def test_no_match_stops_before_policy_assessment():
    """그래프의 오류 경계에서도 해당 없음이 승인·실행으로 이어지지 않는다."""
    from unlockops.common.runtime import failure_event
    from unlockops.common.workflow_contracts import AccessJob
    job = AccessJob(schema_version=2, event_id=UUID(OTHER), problem_id=UUID(RESOURCE), job_type="ANALYZE")
    ctx = context()
    state = {"job": job.model_dump(mode="json"), "context": ctx,
             "intent": {"request_type": "ACCESS_REQUEST", "requested_role": "",
                        "entitlement_selection": {"entitlement_id": None}}}
    class ForbiddenTools:
        async def call(self, *args):
            pytest.fail("후보가 없으면 자격 심사와 실행 도구를 호출하지 않는다")
    result = await graph.assess(deepcopy(state), tools=ForbiddenTools())
    assert result["error"]["code"] == "OUT_OF_SCOPE"
    event = failure_event(job, result["error"]["code"])
    assert event["result"]["status"] == "MANUAL_REVIEW"
    assert event["result"]["reason_code"] == "OUT_OF_SCOPE"
