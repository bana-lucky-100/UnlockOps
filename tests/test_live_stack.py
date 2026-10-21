"""Opt-in real Vue-origin HTTP / Spring / RabbitMQ / two-MCP / Graph integration.

Requires a fresh isolated demo stack. Never starts containers or migrates a DB.
It submits test requests to that stack only when explicitly enabled by its user.
"""
import os
import time

import httpx
import pytest

pytestmark=pytest.mark.skipif(os.getenv("RUN_LIVE_STACK")!="1",reason="Live demo stack not explicitly enabled")


def mutation(client,path,body):
    csrf=client.get("/api/auth/csrf"); csrf.raise_for_status()
    token=csrf.json()
    return client.post(path,json=body,headers={token["headerName"]:token["token"]})


def login(client,login_id):
    response=mutation(client,"/api/auth/login",{"loginId":login_id,"password":os.getenv("DEMO_PASSWORD","demo1234")})
    response.raise_for_status()


def wait_status(client,problem_id,expected):
    end=time.monotonic()+60
    while time.monotonic()<end:
        response=client.get("/api/problems/"+problem_id); response.raise_for_status()
        problem=response.json()
        if problem["status"]==expected: return problem
        if problem["status"] in {"FAILED","REJECTED","MANUAL_REVIEW","DONE"}:
            pytest.fail(f"Expected {expected}, got {problem['status']}: {problem.get('reason_code')}")
        time.sleep(.5)
    pytest.fail("Timed out waiting for worker result")


def test_real_queue_jira_failure_and_designated_approver():
    base=os.getenv("LIVE_BASE_URL","http://localhost:8088")
    with httpx.Client(base_url=base,timeout=15) as requester, \
         httpx.Client(base_url=base,timeout=15) as approver, \
         httpx.Client(base_url=base,timeout=15) as other, \
         httpx.Client(base_url=base,timeout=15) as department_head:
        assert requester.get("/api/problems").status_code==401
        login(requester,"kim_dev"); login(approver,"park_lead"); login(other,"song_ops")
        login(department_head,"yoon_head")
        before=approver.get("/api/approvals/summary"); before.raise_for_status()
        head_before=department_head.get("/api/approvals/summary"); head_before.raise_for_status()
        assert requester.get("/api/problems").status_code==403
        assert requester.post("/api/problems",json={"platform":"JIRA","contents":"PAY"}).status_code==403
        response=mutation(requester,"/api/problems",{"platform":"JIRA","contents":"PAY 프로젝트가 안 보여요","simulateJiraFailure":True})
        response.raise_for_status(); problem_id=response.json()["id"]
        # 생성 직후에는 부서장이 임시 담당자다. 분석 완료 후 TF 승인자로 재배정된다.
        # 신청자는 전 단계에서 조회할 수 있으므로 담당자 변경 전에도 안전하게 기다린다.
        wait_status(requester,problem_id,"WAITING_APPROVAL")
        pending_response=approver.get("/api/problems/"+problem_id)
        pending_response.raise_for_status()
        pending=pending_response.json()
        assert pending["status"]=="WAITING_APPROVAL"
        own=requester.get("/api/problems/"+problem_id)
        own.raise_for_status()
        assert not ({"evidence","plan","plan_hash","approved_plan_hash","thread_id","idempotency_key"} & own.json().keys())
        assert all(set(e["payload"])=={"message"} for e in own.json()["events"])
        mine=requester.get("/api/problems?mine=true"); mine.raise_for_status()
        assert any(p["id"]==problem_id for p in mine.json())
        assert requester.get("/api/approvals/summary").status_code==403
        totals=approver.get("/api/approvals/summary"); totals.raise_for_status()
        assert set(totals.json())=={"department","memberCount","weekRequests","approved","rejected","failed"}
        assert totals.json()["weekRequests"]==before.json()["weekRequests"]+1
        # Both approvers are in the same department, but the TF request belongs only to park_lead.
        head_pending=department_head.get("/api/approvals/summary"); head_pending.raise_for_status()
        assert head_pending.json()==head_before.json()
        assert totals.json()["department"]==head_pending.json()["department"]
        assert totals.json()["memberCount"]==head_pending.json()["memberCount"]
        decision={"approved":True,"expectedPlanHash":pending["plan_hash"],"reason":"통합 시연"}
        assert mutation(other,f"/api/problems/{problem_id}/decision",decision).status_code==403
        accepted=mutation(approver,f"/api/problems/{problem_id}/decision",decision)
        accepted.raise_for_status()
        assert mutation(approver,f"/api/problems/{problem_id}/decision",decision).status_code==409
        failed=wait_status(approver,problem_id,"FAILED")
        attempts={e["payload"]["details"][0]["attempt"] for e in failed["events"]
                  if e["kind"]=="PROGRESS" and e["payload"].get("node")=="execute"}
        assert attempts=={1,2,3}
        assert failed["reason_code"]=="MOCK_JIRA_UNAVAILABLE"
        after=approver.get("/api/approvals/summary"); after.raise_for_status()
        assert after.json()["approved"]==totals.json()["approved"]+1
        assert after.json()["failed"]==totals.json()["failed"]+1
        assert after.json()["weekRequests"]==totals.json()["weekRequests"]
        head_after=department_head.get("/api/approvals/summary"); head_after.raise_for_status()
        assert head_after.json()==head_before.json()
