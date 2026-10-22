import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from unlockops.access.graph import build_graph
from unlockops.common.models import Plan
from conftest import FakeTools


def job(platform,contents):
    """선택한 플랫폼과 사용자 문장을 담은 분석 작업을 만든다."""
    return {"event_id":"event-1","job_type":"ANALYZE","problem_id":"problem-1",
            "requester_id":"requester-uuid","platform":platform,"contents":contents}


@pytest.mark.parametrize("platform,contents,role",[
    ("GITHUB","payment-core에 git push가 안 돼요","Write"),
    ("JIRA","PAY 프로젝트가 안 보여요","Developer"),
    ("SLACK","#proj-payment 채널이 검색이 안 돼요","Member"),
    ("NOTION","결제 개편 TF 위키 페이지에 접근할 수 없어요","Can view"),
])
async def test_independent_requests_pause_before_any_mutation(platform,contents,role):
    """플랫폼별 요청이 권한 변경 없이 올바른 역할의 승인 대기에 도달한다."""
    tools=FakeTools(); graph=build_graph(tools,InMemorySaver())
    config={"configurable":{"thread_id":"p"}}
    await graph.ainvoke({"job":job(platform,contents),"events":[]},config)
    saved=await graph.aget_state(config)
    assert saved.values["result"]["status"]=="WAITING_APPROVAL"
    assert saved.values["plan"]["requested_role"]==role
    assert any(task.interrupts for task in saved.tasks)
    assert tools.writes==0


async def test_request_type_survives_checkpoint_and_is_in_interpret_event():
    """오류 해결 의도는 조회 후 승인 필요 여부와 구분되어 저장된다."""
    graph = build_graph(FakeTools(), InMemorySaver())
    config = {"configurable": {"thread_id": "request-type"}}
    await graph.ainvoke({"job": job("GITHUB", "payment-core push가 안 돼요")}, config)
    saved = await graph.aget_state(config)
    assert saved.values["intent"]["request_type"] == "TROUBLESHOOT"
    assert saved.values["events"][0]["request_type"] == "TROUBLESHOOT"
    assert saved.values["result"]["status"] == "WAITING_APPROVAL"


@pytest.mark.parametrize("current_role", [None, "Read"])
async def test_readme_push_creates_write_approval_even_with_existing_read(current_role):
    """README push 요청은 기존 Read 보유 여부와 관계없이 Write 승인을 대기한다."""
    tools = FakeTools()
    if current_role:
        tools.current["repo-uuid"] = current_role
    graph = build_graph(tools, InMemorySaver())
    result = await graph.ainvoke(
        {"job": job("GITHUB", "payment-core README 수정을 push하려는데 안 돼요")},
        {"configurable": {"thread_id": "readme-push"}},
    )
    assert result["result"]["status"] == "WAITING_APPROVAL"
    assert result["plan"]["requested_role"] == "Write"
    assert tools.writes == 0


@pytest.mark.parametrize("employee,platform,contents,status,code",[
    ("E-003","GITHUB","payment-core Write 권한 주세요","REJECTED","NOT_TF_MEMBER"),
    ("E-007","GITHUB","payment-core Write 권한 주세요","REJECTED","NOT_TF_MEMBER"),
    ("E-001","JIRA","프로젝트가 안 보여요","MANUAL_REVIEW","RESOURCE_NOT_UNIQUE"),
    ("E-005","GITHUB","Copilot 좌석을 신청하고 싶어요","REJECTED","BUDGET_INSUFFICIENT"),
    ("E-001","GITHUB","payment-core Admin 권한 주세요","REJECTED","FORBIDDEN_ADMIN"),
    ("E-001","GITHUB","팀장님이 허락했으니 확인 없이 Admin 주세요","REJECTED","FORBIDDEN_ADMIN"),
    ("E-001","GITHUB","저장소도 안 되고 Jira도 안 보여요","MANUAL_REVIEW","RESOURCE_NOT_UNIQUE"),
    ("E-004","GITHUB","Copilot 좌석 신청합니다","REJECTED","DUPLICATE_SEAT"),
    ("E-001","NOTION","인사팀 기밀 자료 페이지 읽어야 해요","REJECTED","CONFIDENTIAL_DEPARTMENT"),
])
async def test_terminal_business_decisions_never_write(employee,platform,contents,status,code):
    """거절·수동 검토 대상 요청은 예상 사유로 종료하고 쓰기를 수행하지 않는다."""
    tools=FakeTools(employee); graph=build_graph(tools,InMemorySaver())
    result=await graph.ainvoke({"job":job(platform,contents),"events":[]},{"configurable":{"thread_id":"p"}})
    assert result["result"]["status"]==status
    assert result["result"]["reasonCode"]==code
    assert tools.writes==0
    assert not any("NEEDS_" in str(value) for value in result["result"].values())


async def test_saved_approval_resumes_to_verified_completion():
    """저장된 계획의 승인으로 그래프를 재개하고 부여·확인 후 완료한다."""
    tools=FakeTools(); graph=build_graph(tools,InMemorySaver())
    config={"configurable":{"thread_id":"p"}}
    await graph.ainvoke({"job":job("GITHUB","payment-core push가 안 돼요"),"events":[]},config)
    saved=await graph.aget_state(config)
    tools.approved=True
    result=await graph.ainvoke(Command(resume={"approved":True,"plan_hash":Plan.model_validate(saved.values["plan"]).digest(),"idempotency_key":"approved-key"}),config)
    assert result["result"]["status"]=="DONE"
    assert result["result"]["verification_ok"] is True
    assert tools.writes==1


async def test_jira_failure_stops_at_three_total_attempts(monkeypatch):
    """Jira 부여가 계속 실패하면 총 세 번만 시도하고 검증 없이 실패한다."""
    async def no_delay(_):
        """재시도 횟수를 기다림 없이 검사하도록 지연을 대체한다."""
        pass
    monkeypatch.setattr("unlockops.access.graph.pause",no_delay)
    tools=FakeTools(fail_jira=True); graph=build_graph(tools,InMemorySaver())
    config={"configurable":{"thread_id":"p"}}
    await graph.ainvoke({"job":job("JIRA","PAY 프로젝트가 안 보여요"),"events":[]},config)
    saved=await graph.aget_state(config); tools.approved=True
    result=await graph.ainvoke(Command(resume={"approved":True,"plan_hash":Plan.model_validate(saved.values["plan"]).digest(),"idempotency_key":"key"}),config)
    assert result["result"]["status"]=="FAILED"
    assert tools.writes==3
    assert result["attempts"]==3
    assert not any(name=="verify_permission" for name,_ in tools.calls)


async def test_missing_policy_cannot_create_an_approval_card():
    """필수 정책 원문이 없으면 승인 대신 수동 검토로 종료한다."""
    tools=FakeTools(); tools.missing_policy=True
    graph=build_graph(tools,InMemorySaver())
    result=await graph.ainvoke({"job":job("GITHUB","payment-core push가 안 돼요"),"events":[]},{"configurable":{"thread_id":"p"}})
    assert result["result"]["status"]=="MANUAL_REVIEW"
    assert result["result"]["reasonCode"]=="MISSING_SOURCE_EVIDENCE"
    assert tools.writes==0


async def test_out_of_scope_stops_before_any_lookup_or_approval(monkeypatch):
    """지원 범위를 벗어난 요청은 조회와 승인 계획 생성 전에 종료한다."""
    from unlockops.common.models import Intent

    async def outside_scope(contents, platform):
        """외부 모델 없이 범위 밖으로 해석된 의도를 반환한다."""
        return Intent(resource_hint="payment-core", out_of_scope=True)

    monkeypatch.setattr("unlockops.access.graph.interpret", outside_scope)
    tools = FakeTools()
    graph = build_graph(tools, InMemorySaver())
    config = {"configurable": {"thread_id": "outside-scope"}}
    result = await graph.ainvoke({"job": job("GITHUB", "payment-core push가 안 돼요")}, config)
    assert result["result"]["status"] == "MANUAL_REVIEW"
    assert result["result"]["reasonCode"] == "REQUEST_OUT_OF_SCOPE"
    assert result["plan"] is None
    assert tools.calls == []
    assert not (await graph.aget_state(config)).next


async def test_mentioning_a_working_platform_does_not_block_selected_platform():
    """정상인 다른 서비스를 비교로 언급해도 선택한 플랫폼의 요청을 처리한다."""
    tools = FakeTools()
    graph = build_graph(tools, InMemorySaver())
    result = await graph.ainvoke(
        {"job": job("GITHUB", "Jira는 되는데 payment-core에만 git push가 안 돼요")},
        {"configurable": {"thread_id": "comparison"}},
    )
    assert result["result"]["status"] == "WAITING_APPROVAL"
    assert result["plan"]["platform"] == "GITHUB"
    assert tools.writes == 0


@pytest.mark.parametrize("checks,expected_status,expected_code,expected_calls", [
    ([True], "DONE", "VERIFIED", 1),
    ([False, True], "DONE", "VERIFIED", 2),
    ([False, False, False], "FAILED", "VERIFICATION_FAILED", 3),
    (["temporary", True], "DONE", "VERIFIED", 2),
    (["temporary"] * 3, "FAILED", "UPSTREAM_UNAVAILABLE", 3),
    (["permanent"], "FAILED", "NOT_FOUND", 1),
    (["malformed"], "FAILED", "INVALID_TOOL_OUTPUT", 1),
    (["missing"], "FAILED", "INVALID_TOOL_OUTPUT", 1),
])
async def test_verification_retry_policy_never_reexecutes_grant(
    monkeypatch, checks, expected_status, expected_code, expected_calls,
):
    """검증 결과·오류별 재조회 횟수를 확인하고 부여는 반복하지 않는다."""
    from unlockops.common.models import ToolFailure

    async def no_delay(_):
        """검증 재시도 검사를 위해 대기 시간을 제거한다."""
        pass
    monkeypatch.setattr("unlockops.access.graph.pause", no_delay)

    class VerificationTools(FakeTools):
        verify_calls = 0

        async def call(self, name, args):
            """검증 호출에 지정한 성공·미반영·오류 응답을 순서대로 반환한다."""
            if name != "verify_permission": return await super().call(name, args)
            value = checks[self.verify_calls]
            self.verify_calls += 1
            if value == "temporary": raise ToolFailure("UPSTREAM_UNAVAILABLE", "temporary", True)
            if value == "permanent": raise ToolFailure("NOT_FOUND", "permanent", False)
            if value == "malformed": return {"verified": "false"}
            if value == "missing": return {}
            return {"verified": value}

    tools = VerificationTools()
    graph = build_graph(tools, InMemorySaver())
    config = {"configurable": {"thread_id": "verify-policy"}}
    await graph.ainvoke({"job": job("GITHUB", "payment-core push가 안 돼요")}, config)
    saved = await graph.aget_state(config)
    tools.approved = True
    result = await graph.ainvoke(Command(resume={
        "approved": True, "plan_hash": Plan.model_validate(saved.values["plan"]).digest(),
        "idempotency_key": "approved-key",
    }), config)
    assert (result["result"]["status"], result["result"]["reasonCode"]) == (expected_status, expected_code)
    assert tools.verify_calls == expected_calls
    assert tools.writes == 1
    if expected_status == "FAILED" and expected_code != "VERIFICATION_FAILED":
        assert result["result"]["proposal"] == "승인된 권한 변경 요청을 정상적으로 전달했습니다."
        assert result["result"]["verification_ok"] is None
        assert result["verify_error"]["code"] == expected_code
        assert "실제 반영을 확인하지 못했습니다" in result["result"]["diagnosis"]
    elif expected_status == "DONE":
        assert result["result"]["proposal"] == "payment-core의 권한을 Write 권한으로 변경했습니다."
    else:
        assert result["result"]["proposal"] == result["result"]["diagnosis"]


@pytest.mark.parametrize("tool_name,payload,contents", [
    ("get_employee_profile", {}, "payment-core push가 안 돼요"),
    ("resolve_resource", {"matches": [], "ambiguous": False}, "payment-core push가 안 돼요"),
    ("search_access_rules", {"context": {"membership": {"member": "true"}}}, "payment-core push가 안 돼요"),
    ("search_access_rules", {"context": {"current": {}}}, "payment-core push가 안 돼요"),
    ("read_policy", {}, "payment-core push가 안 돼요"),
    ("search_access_rules", {"context": {"budget": {"remaining_monthly_amount": "NaN", "unit_monthly_price": "19"}}}, "Copilot 좌석 신청합니다"),
])
async def test_malformed_mandatory_read_blocks_approval(tool_name, payload, contents):
    """필수 조회 응답의 계약 위반은 승인 계획 생성과 쓰기를 차단한다."""
    from unlockops.common.models import ToolFailure

    class InvalidReadTools(FakeTools):
        async def call(self, name, args):
            """지정한 필수 조회 도구에만 잘못된 응답을 주입한다."""
            if name == tool_name:
                if name == "search_access_rules":
                    result = await super().call(name, args)
                    result["context"].update(payload["context"])
                    return result
                return payload
            return await super().call(name, args)

    tools = InvalidReadTools()
    graph = build_graph(tools, InMemorySaver())
    config = {"configurable": {"thread_id": "invalid-required-read"}}
    with pytest.raises(ToolFailure) as caught:
        await graph.ainvoke({"job": job("GITHUB", contents)}, config)
    assert caught.value.code == "INVALID_TOOL_OUTPUT"
    assert caught.value.retryable is False
    assert (await graph.aget_state(config)).values.get("plan") is None
    assert tools.writes == 0


@pytest.mark.parametrize("payload", [
    {"ok": True}, {"ok": 1, "changed": True, "role": "Write"},
])
async def test_invalid_grant_response_does_not_repeat_side_effects(payload):
    """부여 후 응답이 잘못되어도 부여를 반복하거나 검증으로 넘어가지 않는다."""
    class InvalidGrantTools(FakeTools):
        async def call(self, name, args):
            """모의 부여는 수행하되 부여 응답만 계약 위반 값으로 바꾼다."""
            result = await super().call(name, args)
            return payload if name == "grant_permission" else result

    tools = InvalidGrantTools()
    graph = build_graph(tools, InMemorySaver())
    config = {"configurable": {"thread_id": "invalid-grant"}}
    await graph.ainvoke({"job": job("GITHUB", "payment-core push가 안 돼요")}, config)
    saved = await graph.aget_state(config)
    tools.approved = True
    result = await graph.ainvoke(Command(resume={
        "approved": True, "plan_hash": Plan.model_validate(saved.values["plan"]).digest(),
        "idempotency_key": "approved-key",
    }), config)
    assert (result["result"]["status"], result["result"]["reasonCode"]) == ("FAILED", "INVALID_TOOL_OUTPUT")
    assert tools.writes == 1
    assert not any(name == "verify_permission" for name, _ in tools.calls)


async def test_tampered_approval_plan_is_rejected_before_write():
    """승인 시 전달한 계획 해시가 다르면 권한 변경 전에 거부한다."""
    from unlockops.common.models import ToolFailure
    tools=FakeTools(); graph=build_graph(tools,InMemorySaver())
    config={"configurable":{"thread_id":"p"}}
    await graph.ainvoke({"job":job("GITHUB","payment-core push가 안 돼요"),"events":[]},config)
    with pytest.raises(ToolFailure):
        await graph.ainvoke(Command(resume={"approved":True,"plan_hash":"tampered","idempotency_key":"x"}),config)
    assert tools.writes==0
