"""권한 제안만 모의 LLM으로 검증한다. 답변 생성 프롬프트나 외부 모델은 사용하지 않는다."""

from dataclasses import replace
import json
import shutil

from langgraph.checkpoint.memory import InMemorySaver
import pytest

from conftest import FakeTools, ROOT
from test_scenarios import job
from unlockops import graph as graph_module
from unlockops import permission_proposal
from unlockops_rag.search import DocumentIndex
from unlockops.rules import required_sources


def citations():
    """실제 회사 권한표·규정에서 이번 TF 요청에 필요한 청크 ID를 고른다."""
    company = DocumentIndex(ROOT / "data/company-a-access-matrix.md", "business", {3, 4, 7})
    policy = DocumentIndex(ROOT / "data/policy_corpus.md", "policy")
    keywords = {"A-ACCESS-03": "| GitHub |", "A-ACCESS-04": "payment-core",
                "A-ACCESS-07": "그 TF의 리더", "POL-03": "제2조", "POL-02": "제3조"}
    resource = {"platform": "GITHUB", "access_scope": "TF"}
    return [next(chunk["chunk_id"] for chunk in (company if doc_id.startswith("A-") else policy).read(doc_id)
                 if keywords[doc_id] in chunk["text"]) for doc_id in required_sources(resource)]


def proposal(**changes):
    """정상 제안을 기본값으로 만들고, 테스트마다 바꿀 필드만 덮어쓴다."""
    return {"decision": "PROPOSE", "requested_role": "Write",
            "reason": "실제 TF 구성원이며 회사 권한표의 TF 저장소 Write 조건에 해당합니다.",
            "evidence_ids": citations(), **changes}


class FakeModel:
    """실제 모델 API 대신 준비된 결과를 반환하고 모델에 전달된 입력을 기록한다."""

    def __init__(self, output):
        """모의 모델이 반환할 값 또는 발생시킬 예외를 저장한다."""
        self.output = output
        self.messages = []

    def with_structured_output(self, schema):
        """권한 제안용 응답 형식을 사용했는지 검사한다."""
        assert schema is permission_proposal.PermissionProposal
        return self

    async def ainvoke(self, messages):
        """네트워크 호출 없이 준비된 제안이나 오류를 반환한다."""
        self.messages = messages
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


async def analyze(monkeypatch, output, *, contents="payment-core에 push가 안 돼요", tools=None, llm=True):
    """모델과 MCP만 모의 객체로 바꾸고 실제 그래프의 권한 검토 흐름을 실행한다."""
    # graph의 모드만 바꿔 권한 제안을 테스트한다. 기존 요청 해석 모델은 호출하지 않는다.
    model = FakeModel(output)
    monkeypatch.setattr(permission_proposal, "model", lambda: model)
    monkeypatch.setattr(graph_module, "settings", replace(graph_module.settings, mode="llm" if llm else "demo"))
    tools = tools or FakeTools()
    result = await graph_module.build_graph(tools, InMemorySaver()).ainvoke(
        {"job": job("GITHUB", contents)}, {"configurable": {"thread_id": "permission-proposal"}},
    )
    return result, tools, model


async def test_llm_receives_actual_facts_and_rag_evidence_and_proposes_no_writes(monkeypatch):
    """모델이 실제 직원 사실·원문을 받고, 제안 후에도 승인 전에는 권한을 변경하지 않는지 확인한다."""
    result, tools, model = await analyze(monkeypatch, proposal())
    assert result["result"]["status"] == "WAITING_APPROVAL"
    assert result["plan"]["requested_role"] == "Write"
    assert result["permission_proposal"]["evidence_ids"] == citations()
    payload = json.loads(model.messages[1][1])
    assert payload["membership"]["member"] is True
    assert payload["employee"]["id"] == tools.profile["id"]
    assert "employee_no" not in payload["employee"]
    assert all(chunk["source_hash"] for chunk in payload["evidence"])
    assert any("payment-core" in chunk["text"] for chunk in payload["evidence"])
    judge_event = next(event for event in result["events"] if event["node"] == "judge")
    assert judge_event["source_hashes"]
    assert judge_event["permission_proposal"] == result["permission_proposal"]
    assert judge_event["handling"] == "APPROVAL"
    assert tools.writes == 0


@pytest.mark.parametrize("output,contents,code", [
    (proposal(evidence_ids=["invented:1"]), "payment-core push가 안 돼요", "INVALID_PROPOSAL_EVIDENCE"),
    (proposal(evidence_ids=[]), "payment-core push가 안 돼요", "INVALID_PERMISSION_PROPOSAL"),
    (proposal(evidence_ids=citations()[:1]), "payment-core push가 안 돼요", "INVALID_PROPOSAL_EVIDENCE"),
    (proposal(), "payment-core Read 권한 주세요", "PROPOSAL_ROLE_MISMATCH"),
    (proposal(requested_role="Admin"), "payment-core가 안 보여요", "INVALID_PERMISSION_PROPOSAL"),
    (proposal(decision="MANUAL_REVIEW", requested_role="", evidence_ids=[]), "payment-core push가 안 돼요", "PERMISSION_PROPOSAL_REVIEW"),
    (RuntimeError("provider body must not be exposed"), "payment-core push가 안 돼요", "PERMISSION_MODEL_UNAVAILABLE"),
])
async def test_invalid_or_unavailable_permission_proposal_never_authorizes(monkeypatch, output, contents, code):
    """허위·누락 근거, 역할 변경, 모델 장애가 자동 승인 대신 수동 검토로 끝나는지 확인한다."""
    result, tools, _ = await analyze(monkeypatch, output, contents=contents)
    assert (result["result"]["status"], result["result"]["reasonCode"]) == ("MANUAL_REVIEW", code)
    assert result["plan"] is None
    assert tools.writes == 0
    assert "provider body" not in str(result)


async def test_llm_cannot_bypass_platform_role_family(monkeypatch):
    """GitHub 요청에 Jira Developer를 제안해도 실제 역할군 검사에서 차단되는지 확인한다."""
    result, tools, _ = await analyze(monkeypatch, proposal(requested_role="Developer"), contents="payment-core가 안 보여요")
    assert (result["result"]["status"], result["result"]["reasonCode"]) == ("REJECTED", "ABOVE_ACCESS_CEILING")
    assert result["plan"] is None
    assert tools.writes == 0


async def test_llm_cannot_override_actual_tf_membership(monkeypatch):
    """모델이 Write를 제안해도 실제 TF 비구성원에게는 부여할 수 없는지 확인한다."""
    result, tools, model = await analyze(monkeypatch, proposal(), tools=FakeTools("E-007"))
    assert result["result"]["reasonCode"] == "NOT_TF_MEMBER"
    assert model.messages
    assert tools.writes == 0


async def test_demo_does_not_call_the_permission_model(monkeypatch):
    """데모에서는 모델을 호출하지 않고 원문 권한표와 직원 사실만으로 처리하는지 확인한다."""
    result, tools, model = await analyze(monkeypatch, RuntimeError("must not call"), llm=False)
    assert result["result"]["status"] == "WAITING_APPROVAL"
    assert result["permission_proposal"] is None
    assert model.messages == []
    assert tools.writes == 0


async def test_stale_rag_evidence_stops_before_permission_model(monkeypatch):
    """근거의 원문 해시가 오래됐으면 모델을 부르기 전에 수동 검토로 보내는지 확인한다."""
    class StaleEvidence(FakeTools):
        async def call(self, name, args):
            """본문은 그대로 두고 회사 규정 청크의 해시만 오래된 값으로 바꾼다."""
            output = await super().call(name, args)
            if name == "read_access_rule":
                for chunk in output["chunks"]:
                    chunk["source_hash"] = "stale"
            return output

    result, tools, model = await analyze(monkeypatch, proposal(), tools=StaleEvidence())
    assert (result["result"]["status"], result["result"]["reasonCode"]) == ("MANUAL_REVIEW", "POLICY_EVIDENCE_MISMATCH")
    assert result["plan"] is None
    assert model.messages == []
    assert tools.writes == 0


async def test_existing_rag_document_controls_model_input_and_grant_ceiling(tmp_path, monkeypatch):
    """기존 Markdown만 수정해도 LLM 입력과 실제 실행 상한 양쪽에 반영되는지 확인한다."""
    from unlockops import rules

    # 실제 프로젝트 원문을 수정하지 않도록 임시 폴더에 복사한 뒤 상한을 Write에서 Read로 낮춘다.
    for filename in ("company-a-access-matrix.md", "policy_corpus.md"):
        shutil.copyfile(ROOT / "data" / filename, tmp_path / filename)
    matrix = tmp_path / "company-a-access-matrix.md"
    changed_row = "| GitHub | TF 전용 저장소 (TF 구성원만) | Read | Write | Read |"
    matrix.write_text(matrix.read_text(encoding="utf-8").replace(
        "| GitHub | TF 전용 저장소 (TF 구성원만) | Write | Write | Read |", changed_row,
    ), encoding="utf-8")
    monkeypatch.setattr(rules, "settings", replace(rules.settings, data_dir=tmp_path))

    class CurrentDocumentTools(FakeTools):
        async def call(self, name, args):
            """회사 권한표 조회만 임시 폴더의 수정된 원문으로 바꾼다."""
            if name == "read_access_rule":
                return {"chunks": DocumentIndex(matrix, "business", {3, 4, 7}).read(args["doc_id"])}
            return await super().call(name, args)

    # 모델은 일부러 이전 기준의 Write를 제안한다. 현재 원문 상한이 Read이므로 차단되어야 한다.
    result, tools, model = await analyze(monkeypatch, proposal(), tools=CurrentDocumentTools())
    payload = json.loads(model.messages[1][1])
    assert any(changed_row in chunk["text"] for chunk in payload["evidence"])
    assert result["result"]["reasonCode"] == "ABOVE_ACCESS_CEILING"
    assert result["plan"] is None
    assert tools.writes == 0


@pytest.mark.parametrize("case,expected_handling,expected_status", [
    ("approval", "APPROVAL", "WAITING_APPROVAL"),
    ("not_member", "REJECT", "REJECTED"),
    ("already_has_access", "ANSWER", "DONE"),
    ("guide", "ANSWER", "DONE"),
])
async def test_permission_assessment_and_common_response_work_together(
    monkeypatch, case, expected_handling, expected_status,
):
    """권한 제안과 사용자 설명을 별도로 호출하고, 검증된 판정·근거 이력을 함께 보존한다."""
    from unlockops import answering
    from unlockops.answering import AnswerDraft, AnswerReview, AnswerStep, Citation

    contexts = []

    class ResponseModel:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        async def ainvoke(self, messages):
            payload = json.loads(messages[-1][1])
            if self.schema is AnswerReview:
                assert payload["context"] == contexts[-1]
                return AnswerReview(supported=True)
            contexts.append(payload)
            source = payload["sources"][0]
            return AnswerDraft(answerable=True, steps=[AnswerStep(
                text="확정된 결과에 대한 사용자 안내입니다.",
                citations=[Citation(chunk_id=source["chunk_id"], quote=source["text"][:100])],
            )])

    monkeypatch.setattr(answering, "settings", replace(answering.settings, mode="llm"))
    monkeypatch.setattr(answering, "model", ResponseModel)
    tools = FakeTools("E-007" if case == "not_member" else "E-001")
    if case == "already_has_access":
        tools.current["repo-uuid"] = "Write"
    contents = "payment-core Write 권한 신청 절차를 설명해주세요" if case == "guide" else "payment-core push가 안 돼요"
    state, tools, permission_model = await analyze(monkeypatch, proposal(), tools=tools, contents=contents)
    assert state["handling"] == expected_handling
    assert state["result"]["status"] == expected_status
    assert len(contexts) == 1 and contexts[0]["decision"]["handling"] == expected_handling
    assert "확정된 결과에 대한 사용자 안내" in state["result"]["proposal"]
    assert tools.writes == 0
    judge = next(event for event in state["events"] if event["node"] == "judge")
    if case == "guide":
        assert permission_model.messages == [] and state["permission_proposal"] is None
    else:
        assert permission_model.messages and state["permission_proposal"]
        assert judge["source_hashes"] and judge["evidence_ids"]
        assert judge["permission_proposal"] == state["permission_proposal"]
    if case == "approval":
        assert state["plan"]["requested_role"] == "Write"
    else:
        assert state["plan"] is None and state["result"]["verification_ok"] is None
