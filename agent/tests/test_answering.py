"""답변·승인·거절·수동 검토 및 RAG 근거 검증. 외부 모델은 호출하지 않는다."""

from dataclasses import replace
from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from conftest import FakeTools, ROOT
from test_scenarios import job
from unlockops import answering
from unlockops.answering import AnswerDraft, AnswerReview, AnswerStep, Citation
from unlockops.graph import build_graph
from unlockops.models import Plan, ToolFailure
from unlockops_rag.search import DocumentIndex


class RetrievalTools(FakeTools):
    """실제 문서 검색과 모의 직원·SaaS 조회를 조합한다."""

    def __init__(self, employee="E-001"):
        super().__init__(employee)
        self.index = DocumentIndex(ROOT / "data/policy_corpus.md", "policy")

    async def call(self, name, args):
        if name == "search_policy":
            return {"hits": self.index.search(args["query"], args["platform"])}
        if name == "read_policy":
            return {"chunks": self.index.read(args["doc_id"])}
        return await super().call(name, args)


async def invoke(contents, tools=None, platform="GITHUB"):
    tools = tools or RetrievalTools()
    graph = build_graph(tools, InMemorySaver())
    config = {"configurable": {"thread_id": "answer-path"}}
    state = await graph.ainvoke({"job": job(platform, contents)}, config)
    return state, tools, await graph.aget_state(config)


@pytest.mark.parametrize("contents", [
    "Read와 Write 역할 차이를 설명해주세요",
    "Admin 권한의 의미를 설명해주세요",
    "payment-core Write 권한 신청 절차를 설명해주세요",
])
async def test_guide_answers_without_creating_a_grant_or_requiring_a_resource(contents):
    state, tools, snapshot = await invoke(contents)
    result = state["result"]
    assert result["status"] == "MANUAL_REVIEW"
    assert result["reasonCode"] == "RAG_GUIDANCE"
    assert state["handling"] == "ANSWER"
    assert result["plan"] is None and result["verification_ok"] is None
    assert any(e.get("kind") == "answer_citation" for e in result["evidence"])
    assert "근거:" in result["proposal"]
    assert tools.writes == 0 and not snapshot.next


@pytest.mark.parametrize("contents", [
    "payment-core Write 권한은 있는데 push할 때 403이 나요",
    "payment-core Write 권한 주세요",
])
async def test_existing_permission_produces_guidance_for_errors_or_access_requests(contents):
    tools = RetrievalTools()
    tools.current["repo-uuid"] = "Write"
    state, tools, _ = await invoke(contents, tools)
    assert state["result"]["status"] == "MANUAL_REVIEW"
    assert state["result"]["reasonCode"] == "RAG_GUIDANCE"
    assert state["handling"] == "ANSWER"
    assert "현재 권한은 Write" in state["result"]["proposal"]
    assert state["result"]["verification_ok"] is None and tools.writes == 0


@pytest.mark.parametrize("contents,status,handling", [
    ("payment-core push가 안 돼요", "WAITING_APPROVAL", "APPROVAL"),
    ("payment-core Admin 권한 주세요", "REJECTED", "REJECT"),
    ("어느 프로젝트인지 모르겠는데 접근이 안 돼요", "MANUAL_REVIEW", "MANUAL_REVIEW"),
])
async def test_facts_route_errors_and_requests_through_existing_guards(contents, status, handling):
    state, tools, _ = await invoke(contents)
    assert state["result"]["status"] == status and state["handling"] == handling
    assert tools.writes == 0


async def test_absent_answer_sources_require_manual_review():
    state, tools, _ = await invoke("Read와 Write 차이를 설명해주세요", FakeTools())
    assert state["result"]["status"] == "MANUAL_REVIEW"
    assert state["result"]["reasonCode"] == "ANSWER_SOURCE_UNAVAILABLE"
    assert state["handling"] == "MANUAL_REVIEW" and tools.writes == 0


async def test_uncovered_technical_topic_does_not_answer_with_unrelated_policy():
    state, tools, _ = await invoke("payment-core에서 git remote 설정은 어떻게 확인하나요?")
    assert state["result"]["status"] == "MANUAL_REVIEW"
    assert state["result"]["reasonCode"] == "ANSWER_SOURCE_UNAVAILABLE"
    assert state["plan"] is None and tools.writes == 0


async def test_push_with_existing_read_requests_missing_write():
    tools = RetrievalTools()
    tools.current["repo-uuid"] = "Read"
    state, tools, _ = await invoke("payment-core Read 권한은 있는데 push가 안 돼요", tools)
    assert state["result"]["status"] == "WAITING_APPROVAL"
    assert state["plan"]["requested_role"] == "Write" and tools.writes == 0


async def test_optional_exact_document_read_can_supply_answer_evidence(monkeypatch):
    class NoSearchHits(RetrievalTools):
        async def call(self, name, args):
            if name == "search_policy": return {"hits": []}
            return await super().call(name, args)

    async def investigate(scoped, profile, resource, contents):
        await scoped.read("read_policy", {"doc_id": "GH-OFF-02"}, optional=True)
        return "complete"

    monkeypatch.setattr("unlockops.graph.investigate", investigate)
    tools = NoSearchHits()
    tools.current["repo-uuid"] = "Write"
    state, _, _ = await invoke("payment-core push가 안 돼요", tools)
    assert state["result"]["status"] == "MANUAL_REVIEW"
    assert state["result"]["reasonCode"] == "RAG_GUIDANCE"
    assert any(e.get("doc_id") == "GH-OFF-02" for e in state["result"]["evidence"])


def answer_state():
    chunk = {"chunk_id": "GH-OFF-02:summary", "doc_id": "GH-OFF-02",
             "text": "팀 멤버십이 있는데도 push가 안 되면 팀의 저장소 역할을 확인합니다."}
    return {"job": job("GITHUB", "payment-core push가 안 돼요"),
            "intent": {"request_type": "TROUBLESHOOT"}, "resource": {}, "current": {"role": "Write"},
            "result": {"diagnosis": "필요한 권한을 보유하고 있습니다."}, "answer_sources": [chunk]}


@pytest.mark.parametrize("fault,expected", [
    (None, "RAG_GUIDANCE"),
    ("unknown_id", "INVALID_ANSWER_EVIDENCE"),
    ("invented_quote", "INVALID_ANSWER_EVIDENCE"),
    ("unsupported_claim", "ANSWER_NOT_GROUNDED"),
    ("unanswerable", "ANSWER_SOURCE_UNAVAILABLE"),
])
async def test_llm_answers_are_checked_against_sources_and_reviewed(monkeypatch, fault, expected):
    state = answer_state()
    calls = []
    class FakeModel:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        async def ainvoke(self, messages):
            calls.append(self.schema)
            if self.schema is AnswerReview:
                return AnswerReview(supported=fault != "unsupported_claim")
            return AnswerDraft(answerable=fault != "unanswerable", steps=[AnswerStep(
                text="팀의 저장소 역할을 담당자와 확인하세요.",
                citations=[Citation(
                    chunk_id="unknown" if fault == "unknown_id" else "GH-OFF-02:summary",
                    quote="문서에 없는 명령어" if fault == "invented_quote" else "팀의 저장소 역할을 확인합니다.",
                )],
            )])
    monkeypatch.setattr(answering, "settings", replace(answering.settings, mode="llm"))
    monkeypatch.setattr(answering, "model", FakeModel)
    draft, reason = await answering.generate_answer(state)
    assert reason == expected
    assert (draft is not None) == (fault is None)
    assert (AnswerReview in calls) == (fault in {None, "unsupported_claim"})


async def test_answer_model_outage_is_a_technical_failure(monkeypatch):
    class BrokenModel:
        def with_structured_output(self, schema): return self
        async def ainvoke(self, messages): raise RuntimeError("provider secret")
    monkeypatch.setattr(answering, "settings", replace(answering.settings, mode="llm"))
    monkeypatch.setattr(answering, "model", BrokenModel)
    with pytest.raises(ToolFailure, match="Answer generation failed") as error:
        await answering.generate_answer(answer_state())
    assert error.value.code == "MODEL_UNAVAILABLE"


async def test_cross_platform_sources_cannot_ground_an_answer():
    state = answer_state()
    state["answer_sources"][0]["doc_id"] = "JR-OFF-01"
    draft, code = await answering.generate_answer(state)
    assert draft is None and code == "ANSWER_SOURCE_UNAVAILABLE"


@pytest.mark.parametrize("contents,handling", [
    ("payment-core push가 안 돼요", "APPROVAL"),
    ("payment-core Admin 권한 주세요", "REJECT"),
    ("어느 프로젝트인지 모르겠는데 접근이 안 돼요", "MANUAL_REVIEW"),
])
@pytest.mark.parametrize("failure", [None, "unavailable", "invalid_evidence"])
async def test_common_response_preserves_decision_and_plan(monkeypatch, contents, handling, failure):
    """각 경로에서 proposal만 교체하고 생성·검증 실패에도 판정과 승인 대기를 유지한다."""
    seen = []

    async def generate(state):
        seen.append(deepcopy(state))
        if failure == "unavailable":
            raise ToolFailure("MODEL_UNAVAILABLE", "provider secret")
        if failure:
            return None, "INVALID_ANSWER_EVIDENCE"
        return AnswerDraft(answerable=True, steps=[AnswerStep(
            text="확정된 판정에 대한 설명입니다.",
            citations=[Citation(chunk_id="source-1", quote="관련 규정")],
        )]), "RAG_GUIDANCE"

    monkeypatch.setattr("unlockops.graph.generate_answer", generate)
    state, tools, snapshot = await invoke(contents)
    assert len(seen) == 1 and seen[0]["handling"] == handling
    before = seen[0]
    assert before["response_context"]["decision"]["handling"] == handling
    assert state["plan"] == before["plan"] and state["handling"] == handling
    assert {k: v for k, v in state["result"].items() if k != "proposal"} == {
        k: v for k, v in before["result"].items() if k != "proposal"
    }
    if failure:
        assert state["result"] == before["result"]
    else:
        assert "확정된 판정에 대한 설명" in state["result"]["proposal"]
    assert tools.writes == 0
    assert snapshot.next == (("approval",) if handling == "APPROVAL" else ())


@pytest.mark.parametrize("handling,status", [
    ("APPROVAL", "WAITING_APPROVAL"), ("REJECT", "REJECTED"),
    ("MANUAL_REVIEW", "MANUAL_REVIEW"),
])
@pytest.mark.parametrize("supported", [True, False])
async def test_common_llm_response_is_reviewed_against_fixed_decision(monkeypatch, handling, status, supported):
    """일반 안내 이외의 경로도 동일한 판정·근거로 생성하고 불일치 검토 결과를 거부한다."""
    import json

    state = answer_state()
    state["handling"] = handling
    state["result"].update(status=status, reasonCode="FIXED_DECISION")
    contexts = []

    class FakeModel:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        async def ainvoke(self, messages):
            payload = json.loads(messages[-1][1])
            contexts.append(payload if self.schema is AnswerDraft else payload["context"])
            if self.schema is AnswerReview:
                return AnswerReview(supported=supported)
            return AnswerDraft(answerable=True, steps=[AnswerStep(
                text="판정 설명" if supported else "승인 및 권한 변경을 완료했습니다.",
                citations=[Citation(chunk_id="GH-OFF-02:summary", quote="팀의 저장소 역할을 확인합니다.")],
            )])

    monkeypatch.setattr(answering, "settings", replace(answering.settings, mode="llm"))
    monkeypatch.setattr(answering, "model", FakeModel)
    draft, code = await answering.generate_answer(state)
    assert (draft is not None) == supported
    assert code == ("RAG_GUIDANCE" if supported else "ANSWER_NOT_GROUNDED")
    assert len(contexts) == 2 and contexts[0] == contexts[1]
    assert contexts[0]["decision"]["status"] == status


async def test_guidance_outage_falls_back_to_manual_review(monkeypatch):
    async def unavailable(state):
        raise ToolFailure("MODEL_UNAVAILABLE", "provider secret")

    monkeypatch.setattr("unlockops.graph.generate_answer", unavailable)
    state, tools, snapshot = await invoke("Read와 Write 역할 차이를 설명해주세요")
    assert state["result"]["status"] == "MANUAL_REVIEW"
    assert state["result"]["reasonCode"] == "MODEL_UNAVAILABLE"
    assert "provider secret" not in state["result"]["proposal"]
    assert state["plan"] is None and not snapshot.next and tools.writes == 0


async def test_composed_approval_resumes_without_regenerating_or_changing_plan_hash(monkeypatch):
    calls = []

    async def generate(state):
        calls.append(Plan.model_validate(state["plan"]).digest())
        return AnswerDraft(answerable=True, steps=[AnswerStep(
            text="Write 권한 부여를 위해 지정 승인자의 승인이 필요합니다.",
            citations=[Citation(chunk_id="source-1", quote="승인 필요")],
        )]), "RAG_GUIDANCE"

    monkeypatch.setattr("unlockops.graph.generate_answer", generate)
    tools = FakeTools()
    graph = build_graph(tools, InMemorySaver())
    config = {"configurable": {"thread_id": "composed-approval"}}
    waiting = await graph.ainvoke({"job": job("GITHUB", "payment-core push가 안 돼요")}, config)
    digest = Plan.model_validate(waiting["plan"]).digest()
    assert calls == [digest]
    assert waiting["result"]["plan"] == waiting["plan"]
    tools.approved = True
    completed = await graph.ainvoke(Command(resume={
        "approved": True, "plan_hash": digest, "idempotency_key": "approved-key",
    }), config)
    assert completed["result"]["status"] == "DONE" and tools.writes == 1
    assert completed["result"]["proposal"] == "payment-core의 권한을 Write 권한으로 변경했습니다."
    assert calls == [digest]
