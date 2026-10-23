"""Reclaim citation regression checks; models are fake and no policy leaves the process."""
import json
import logging
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from unlockops.common.settings import settings
from unlockops.reclaim import narration, policy, reporting
from test_reclaim_agent_design import SnapshotTools, candidate, invoke
from test_workflows import policy_reply


RULES = (
    "## POL-06 | COMMON | v1.1 | 제5조(회수 점검)\n\n문서: 테스트 전용 규정\n\n"
    "시연 정책은 매일 09:00 점검을 가정한다. "
    "TF가 종료된 뒤 30일 이상 미사용이고 다른 활성 TF와 유효 유지 승인이 없는 좌석은 회수 후보다. "
    "퇴사한 직원이 보유한 유료 좌석도 회수 후보다. "
    "회수는 담당자가 결정한다."
)
SOURCE = {"doc_id": "SYNTHETIC-TEST", "article": "POL-06 | COMMON | v1.1 | 제5조(회수 점검)",
          "version": "3", "source_hash": "a" * 64, "text": RULES}
TEMPLATE = "서버에서 확인한 회수 검토 후보입니다."


def facts(reason="TF_ENDED_UNUSED_30D"):
    return {key: deepcopy(value) for key, value in candidate(candidate_reason_code=reason).items()
            if key in narration.FACT_KEYS}


def install_model(monkeypatch, *, draft=None, supported=True, fail_at=None):
    calls = []
    output = {"facts_summary": "서버가 해당 좌석을 회수 검토 대상으로 분류했습니다.",
              "reason": "서버의 사유 코드와 규정에 따라 담당자의 회수 검토가 필요합니다.",
              "next_action": "담당자가 업무상 필요 여부를 확인하고 회수 여부를 결정해야 합니다.",
              "source_indexes": [0], **(draft or {})}

    class FakeModel:
        def with_structured_output(self, schema):
            class Call:
                async def ainvoke(self, messages):
                    context = json.loads(messages[1][1])
                    calls.append((schema, context, messages[0][1]))
                    if schema is fail_at:
                        raise RuntimeError("private provider response must not appear in logs")
                    if schema is narration.ReclaimReview:
                        return {"reason": "입력과 보고서의 사실 일치 여부를 확인했습니다.", "supported": supported}
                    return output
            return Call()

    monkeypatch.setattr(narration, "settings", replace(settings, mode="llm"))
    monkeypatch.setattr(narration, "model", FakeModel)
    return calls


@pytest.mark.parametrize("reason,expected,excluded", [
    ("TF_ENDED_UNUSED_30D", "TF가 종료", "퇴사한 직원"),
    ("EMPLOYEE_LEFT", "퇴사한 직원", "TF가 종료"),
])
def test_sources_are_verbatim_sentences_selected_by_reason(reason, expected, excluded):
    evidence = [deepcopy(SOURCE)]
    previous = deepcopy(evidence)
    sources = policy.report_sources(evidence, reason)
    assert sources and all(s["text"] in RULES for s in sources)
    assert all(expected in s["text"] and excluded not in s["text"] for s in sources)
    assert all("09:00" not in s["text"] and "문서:" not in s["text"] for s in sources)
    assert all(s["version"] == "3" and s["article"] == SOURCE["article"] for s in sources)
    assert evidence == previous


@pytest.mark.parametrize("revision", [2, 3])
@pytest.mark.parametrize("reason", ["TF_ENDED_UNUSED_30D", "EMPLOYEE_LEFT"])
def test_real_frozen_policy_formats_keep_exact_source_identity_offline(revision, reason):
    # Only extraction is tested here; these repository documents are never sent to a real model.
    root = Path(__file__).resolve().parents[2]
    content = (root / f"data/phase2/policies/company-a-policy-v{revision}.md").read_text()
    evidence = [{**SOURCE, "article": a, "text": t} for a, t in policy._policy_sections(content).items()]
    excerpts = policy.report_sources(evidence, reason)
    assert excerpts
    assert all(e["text"] in next(x["text"] for x in evidence if x["article"] == e["article"]) for e in excerpts)
    assert all("09:00" not in e["text"] for e in excerpts)


def test_timing_calculation_cannot_replace_the_candidate_selection_rule():
    source = {**SOURCE, "text": RULES + " TF 종료 후 미사용 시작 시점은 종료일과 마지막 사용일 중 늦은 시점이다."}
    selected = policy.report_sources([source], "TF_ENDED_UNUSED_30D")
    assert len(selected) == 1
    assert "회수 후보다" in selected[0]["text"]


async def test_rephrased_explanation_does_not_rewrite_the_copied_quote(monkeypatch):
    calls = install_model(monkeypatch, draft={"reason": "서버 판정에 따라 회수 후보로 봅니다."})
    private_facts = {**facts(), "employee_name": "do-not-send", "email": "private@example.com"}
    text, mode = await narration.report(private_facts, [SOURCE], TEMPLATE, guidance="테스트 작성 지침")
    assert mode == "llm"
    assert "회수 후보로 봅니다." in text  # Paraphrase is allowed in explanation, not in the quotation.
    excerpt = policy.report_sources([SOURCE], "TF_ENDED_UNUSED_30D")[0]["text"]
    assert f"> {excerpt}" in text
    assert "문서 SYNTHETIC-TEST, 버전 3" in text
    assert "월 예상 검토 금액 19.00 USD" in text
    assert "SYNTHETIC_CONTRACT, 시연 가정값" in text
    assert narration.NO_CHANGE in text
    assert [s for s, _, _ in calls] == [narration.ReclaimDraft, narration.ReclaimReview]
    reviewed = calls[1][1]
    assert reviewed["draft"]["reason"] == "서버 판정에 따라 회수 후보로 봅니다."
    assert "report" not in reviewed  # Review prose, not mechanically copied quotes as model-written text.
    assert reviewed["server_meaning"]["price_source_labels"]["SYNTHETIC_CONTRACT"] == "시연 가정값"
    assert "테스트 작성 지침" in calls[0][2]
    assert "private@example.com" not in json.dumps(calls[0][1])
    assert "employee_name" not in json.dumps(calls[0][1])
    assert "quotes" not in narration.ReclaimDraft.model_fields


@pytest.mark.parametrize("draft", [
    {"source_indexes": [-1]}, {"source_indexes": [99]}, {"source_indexes": [0, 0]},
    {"source_indexes": []}, {"source_indexes": [True]}, {"source_indexes": ["0"]},
    {"facts_summary": " "}, {"quotes": ["인용을 바꿔 쓰면 안 됩니다."]},
])
async def test_invalid_source_selection_or_output_falls_back_before_review(monkeypatch, draft):
    calls = install_model(monkeypatch, draft=draft)
    assert await narration.report(facts(), [SOURCE], TEMPLATE) == (TEMPLATE, "template")
    assert len(calls) == 1


@pytest.mark.parametrize("field,value", [
    ("candidate_status", "RETAINED"), ("review_required", True), ("action_taken", "REVOKED"),
    ("candidate_reason_code", "UNKNOWN"), ("exclusion_reason_code", "ACTIVE_OTHER_TF"),
])
async def test_ineligible_facts_never_call_model(monkeypatch, field, value):
    calls = install_model(monkeypatch)
    assert await narration.report({**facts(), field: value}, [SOURCE], TEMPLATE) == (TEMPLATE, "template")
    assert calls == []


async def test_demo_and_missing_relevant_source_skip_model(monkeypatch):
    calls = install_model(monkeypatch)
    assert await narration.report(facts(), [], TEMPLATE) == (TEMPLATE, "template")
    price_source = {**SOURCE, "article": "GH-OFF-03 | 핵심 요약", "text": "제품 가격 예시입니다."}
    assert await narration.report(facts(), [price_source], TEMPLATE) == (TEMPLATE, "template")
    monkeypatch.setattr(narration, "settings", replace(settings, mode="demo"))
    assert await narration.report(facts(), [SOURCE], TEMPLATE) == (TEMPLATE, "template")
    assert calls == []


@pytest.mark.parametrize("fail_at", [narration.ReclaimDraft, narration.ReclaimReview])
async def test_model_failure_logs_stage_code_without_input_or_provider_text(monkeypatch, caplog, fail_at):
    install_model(monkeypatch, fail_at=fail_at)
    with caplog.at_level(logging.INFO, logger=narration.__name__):
        assert await narration.report(facts(), [SOURCE], TEMPLATE) == (TEMPLATE, "template")
    assert "MODEL_OR_OUTPUT_ERROR" in caplog.text
    assert "private provider response" not in caplog.text and RULES not in caplog.text


async def test_semantic_rejection_still_returns_checked_template(monkeypatch):
    calls = install_model(monkeypatch, draft={"reason": "회수가 완료됐습니다."}, supported=False)
    assert await narration.report(facts(), [SOURCE], TEMPLATE) == (TEMPLATE, "template")
    assert len(calls) == 2


@pytest.mark.parametrize("basis,label", [
    ("SYNTHETIC_CONTRACT", "시연 가정값"), ("CONTRACT", "계약 기록"), ("PUBLIC_LIST_PRICE", "공식 정가 기록"),
])
async def test_report_copies_actual_amount_currency_and_price_basis(monkeypatch, basis, label):
    install_model(monkeypatch)
    observed = facts()
    observed["cost_impact"].update(monthly_amount="16.00", currency="EUR", basis=basis)
    text, mode = await narration.report(observed, [SOURCE], TEMPLATE)
    assert mode == "llm"
    assert f"16.00 EUR (출처: {basis}, {label})" in text
    assert "19.00 USD" not in text


async def test_graph_uses_new_narration_without_changing_frozen_decisions(monkeypatch):
    calls = install_model(monkeypatch)
    original = candidate()
    state = await invoke(SnapshotTools([[original]]))
    event = state["result_event"]
    assert event["result"]["status"] == "EXECUTING"
    assert event["result"]["scan_complete"] is True
    row = event["targets"][0]
    assert row["generation_mode"] == "llm"
    assert all(row[k] == v for k, v in original.items() if k not in {"explanation", "generation_mode"})
    assert row["policy_evidence"] == original["policy_evidence"]  # Excerpts stay internal, wire evidence is unchanged.
    assert state["report_payload"]["candidates"][0]["explanation"] == row["explanation"]
    assert len(calls) == 2
    assert reporting.report is narration.report
