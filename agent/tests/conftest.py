from copy import deepcopy
from pathlib import Path
import os

# .env에 유료 모델 설정이 있어도 테스트는 모의 도구와 로컬 검색만 사용한다.
os.environ["AGENT_MODE"] = "demo"
os.environ["EMBEDDING_BASE_URL"] = ""
os.environ["EMBEDDING_MODEL"] = ""

import pytest

ROOT = Path(__file__).resolve().parents[2]


class FakeTools:
    """그래프 테스트용 모의 MCP다. 실제 서버·DB 통합 테스트를 대신하지는 않는다."""
    descriptions = {}
    def __init__(self, employee="E-001", fail_jira=False):
        self.employee=employee
        self.fail_jira=fail_jira
        self.approved=False
        self.writes=0
        self.current={}
        self.calls=[]
        self.missing_policy=False
        self.member=employee not in {"E-003", "E-007"}
        self.profile={"id":"requester-uuid","employee_no":employee,"department_id":"dev", "department_name":"개발팀",
                      "job_grade":"사원","job_family":"DEV","head_id":"head-uuid"}
        if employee=="E-003": self.profile.update(department_id="ops",job_family="NON_DEV",job_grade="대리")
        if employee=="E-007": self.profile.update(job_grade="대리")
        if employee=="E-005": self.profile.update(department_id="data",job_grade="대리")
        if employee=="E-004": self.profile.update(job_grade="과장")
        self.resources=[
            {"id":"repo-uuid","external_id":"payment-core","name":"payment-core","platform":"GITHUB","access_scope":"TF"},
            {"id":"jira-uuid","external_id":"PAY","name":"PAY","platform":"JIRA","access_scope":"TF"},
            {"id":"slack-uuid","external_id":"#proj-payment","name":"#proj-payment","platform":"SLACK","access_scope":"TF"},
            {"id":"notion-uuid","external_id":"pay-wiki","name":"결제 개편 TF 위키","platform":"NOTION","access_scope":"TF","security_grade":"INTERNAL"},
            {"id":"seat-uuid","external_id":"copilot-seat","name":"Copilot","platform":"GITHUB","access_scope":"SEAT"},
            {"id":"secret-uuid","external_id":"hr-confidential","name":"인사팀 기밀 자료","platform":"NOTION","access_scope":"CONFIDENTIAL","security_grade":"CONFIDENTIAL","designated_department_id":"hr"},
        ]

    async def call(self,name,args):
        from unlockops.models import ToolFailure
        self.calls.append((name,deepcopy(args)))
        if name=="get_employee_profile": return deepcopy(self.profile)
        if name=="resolve_resource":
            matches=[deepcopy(r) for r in self.resources if r["platform"]==args["platform"] and
                     (r["external_id"].casefold() in args["hint"].casefold() or r["name"].casefold() in args["hint"].casefold())]
            return {"matches":matches,"ambiguous":len(matches)!=1}
        if name=="search_policy": return {"hits":[]}
        if name in {"read_policy","read_access_rule"}:
            if self.missing_policy and args["doc_id"]=="POL-03": return {"chunks":[]}
            # 가짜 문장 대신 실제 RAG 원문 청크를 반환해야 문서 해시 검증까지 테스트할 수 있다.
            from unlockops_rag.search import DocumentIndex
            filename = "policy_corpus.md" if name == "read_policy" else "company-a-access-matrix.md"
            kind = "policy" if name == "read_policy" else "business"
            return {"chunks": DocumentIndex(ROOT / "data" / filename, kind).read(args["doc_id"])}
        if name=="search_access_rules": return {"hits":[],"maximum_role":"Write"}
        if name=="get_tf_membership": return {"member":self.member,"leader_id":"leader-uuid"}
        if name=="get_current_permissions":
            role="Seat" if args["resource_id"]=="seat-uuid" and self.employee=="E-004" else self.current.get(args["resource_id"])
            return {"role":role}
        if name=="check_budget": return {"budget":{"remaining_monthly_amount":"10" if self.employee=="E-005" else "150","unit_monthly_price":"19"}}
        if name=="grant_permission":
            self.writes+=1
            if not self.approved: raise ToolFailure("APPROVAL_REQUIRED","not approved")
            if self.fail_jira: raise ToolFailure("MOCK_JIRA_UNAVAILABLE","outage",True)
            self.current["jira-uuid"]="Developer"
            self.current["repo-uuid"]="Write"
            return {"ok":True}
        if name=="verify_permission": return {"verified":self.current.get(args["resource_id"])==args["requested_role"]}
        raise AssertionError("Unexpected tool "+name)


@pytest.fixture
def fake_tools(): return FakeTools()
