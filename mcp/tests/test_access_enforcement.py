"""모의 저장소 연결로 실행 전 검증을 확인한다. 실제 DB 트랜잭션 검증은 별도다."""

from copy import deepcopy

import pytest

from unlockops.models import Plan
from unlockops_mcp.repository import Repository
from unlockops_rag.search import DocumentIndex
from unlockops.settings import settings


def evidence():
    """승인된 TF 저장소 계획에 필요한 실제 RAG 원문 청크를 준비한다."""
    index = DocumentIndex(settings.data_dir / "company-a-access-matrix.md", "business", {3, 4, 7})
    chunks = [chunk for doc_id in index.documents for chunk in index.read(doc_id)]
    policy = DocumentIndex(settings.data_dir / "policy_corpus.md", "policy")
    return chunks + policy.read("POL-03") + policy.read("POL-02")


class Connection:
    """필요한 SELECT 결과를 돌려주고 변경 SQL을 기록하는 모의 DB 연결이다."""

    def __init__(self, problem, actor):
        """승인 요청·승인자·기존 영수증과 변경 내역을 저장한다."""
        self.problem, self.actor = problem, actor
        self.receipt = None
        self.writes = []
        self.teams = []  # current()가 실제 SQL 조회 경로로 읽는 모의 팀 멤버십

    def __enter__(self):
        """실제 연결처럼 with 구문에서 사용할 수 있게 한다."""
        return self

    def __exit__(self, *args):
        """실제 DB에 연결하지 않으므로 종료 시 처리할 자원은 없다."""
        pass

    def execute(self, query, args=()):
        """조회 종류에 맞는 행을 준비하고 쓰기 SQL은 실행 대신 기록한다."""
        self.row = None
        if "SELECT * FROM problems" in query:
            self.row = self.problem
        elif "SELECT result FROM grant_receipts" in query:
            self.row = self.receipt
        elif "SELECT id,role,job_grade FROM users" in query:
            self.row = self.actor
        elif "SELECT id FROM github_teams" in query:
            self.row = {"id": "team"}
        elif "FROM github_team_members" in query:
            self.rows = deepcopy(self.teams)
        elif query.lstrip().startswith(("INSERT", "UPDATE", "DELETE")):
            self.writes.append((query, args))
            if query.startswith("INSERT INTO github_team_members"):
                self.teams.append({"id": args[0], "saas_role": "Write"})
        elif "pg_advisory_xact_lock" not in query:
            raise AssertionError("Unexpected query: " + query)
        return self

    def fetchone(self):
        """직전 SELECT에 해당하는 모의 행을 반환한다."""
        return self.row

    def fetchall(self):
        """실제 current()의 GitHub 팀 조회 결과를 반환한다."""
        return self.rows


@pytest.fixture
def repository(monkeypatch):
    """정상 승인 계획과 현재 직원 사실을 준비하고 저장소의 DB 연결만 교체한다."""
    plan = Plan(problem_id="problem", requester_id="requester", platform="GITHUB",
                resource_id="repo", resource_key="payment-core", requested_role="Write")
    problem = {
        "idempotency_key": "execution-key", "status": "EXECUTING", "decision_source": "HUMAN",
        "decided_at": "approved", "decided_by": "leader", "approved_plan_hash": plan.digest(),
        "plan_hash": plan.digest(), "plan": plan.model_dump(mode="json"), "requester_id": "requester",
        "platform": "GITHUB", "resource_id": "repo", "requested_role": "Write",
        "simulate_jira_failure": False, "evidence": evidence(),
    }
    # 계획 해시는 실제 Plan.digest()로 만든다. 권한 부여 로직 자체는 대체하지 않는다.
    connection = Connection(problem, {"id": "leader", "role": "APPROVER", "job_grade": "과장"})
    repo = Repository()
    membership = {"member": True, "leader_id": "leader"}
    monkeypatch.setattr(repo, "connect", lambda: connection)
    monkeypatch.setattr(repo, "profile", lambda *_: {"id": "requester", "job_grade": "사원", "job_family": "DEV",
                                                   "department_id": "dev", "head_id": "head"})
    monkeypatch.setattr(repo, "resource", lambda *_: {"id": "repo", "external_id": "payment-core",
                                                    "platform": "GITHUB", "access_scope": "TF"})
    monkeypatch.setattr(repo, "membership", lambda *_: deepcopy(membership))
    monkeypatch.setattr(repo, "current", lambda *_: {})
    monkeypatch.setattr(repo, "budget", lambda *_, **__: None)
    return repo, connection, membership


def test_human_approved_current_policy_and_evidence_can_execute(repository):
    """사람 승인·현재 자격·RAG 근거가 모두 맞을 때만 변경 SQL이 만들어지는지 확인한다."""
    repo, connection, _ = repository
    assert repo.grant("problem", "execution-key")["changed"] is True
    assert len(connection.writes) == 3  # 팀 멤버십, 권한, 영수증


@pytest.mark.parametrize("change,expected", [
    ("unapproved", "APPROVAL_REQUIRED"),
    ("plan_changed", "PLAN_CHANGED"),
    ("wrong_actor", "APPROVER_CHANGED"),
    ("missing_evidence", "PRECONDITION_CHANGED"),
    ("stale_evidence", "PRECONDITION_CHANGED"),
    ("membership_changed", "PRECONDITION_CHANGED"),
])
def test_invalid_approval_or_current_preconditions_never_write(repository, change, expected):
    """승인·계획·승인자·근거·소속 중 하나라도 맞지 않으면 쓰기가 전혀 없는지 확인한다."""
    repo, connection, membership = repository
    if change == "unapproved": connection.problem["decision_source"] = "AGENT"
    if change == "plan_changed": connection.problem["approved_plan_hash"] = "changed"
    if change == "wrong_actor": connection.actor["id"] = "head"
    if change == "missing_evidence": connection.problem["evidence"] = []
    if change == "stale_evidence":
        for chunk in connection.problem["evidence"]:
            chunk["source_hash"] = "old-version"
    if change == "membership_changed": membership["member"] = False
    result = repo.grant("problem", "execution-key")
    assert result["error_code"] == expected
    assert connection.writes == []


def test_completed_execution_returns_receipt_without_reapplying(repository):
    """완료 작업이 다시 전달되면 이전 영수증만 반환하고 권한을 중복 부여하지 않는지 확인한다."""
    repo, connection, _ = repository
    previous = {"ok": True, "changed": True, "role": "Write"}
    connection.receipt = {"result": previous}
    assert repo.grant("problem", "execution-key") == previous
    assert connection.writes == []


@pytest.mark.parametrize("roles,expected", [
    ([], None), (["Read"], "Read"), (["Write"], "Write"),
    (["Write", "Read"], "Write"), (["Read", "Write"], "Write"),
])
def test_github_current_reads_existing_team_memberships(repository, monkeypatch, roles, expected):
    """팀 멤버십이 있을 때도 실제 current()가 오류 없이 가장 높은 역할을 고른다."""
    repo, connection, _ = repository
    monkeypatch.setattr(repo, "current", Repository.current.__get__(repo))
    connection.teams = [{"id": f"team-{i}", "saas_role": role} for i, role in enumerate(roles)]
    result = repo.current("requester", "repo")
    assert result["role"] == expected
    assert result["teams"] == [row["id"] for row in connection.teams]
    assert connection.writes == []


def test_approved_github_grant_can_be_read_back_and_verified(repository, monkeypatch):
    """current()를 대체하지 않고, 부여 전 조회부터 부여 후 재조회·검증까지 실행한다."""
    repo, connection, _ = repository
    monkeypatch.setattr(repo, "current", Repository.current.__get__(repo))
    assert repo.current("requester", "repo")["role"] is None
    assert repo.grant("problem", "execution-key")["changed"] is True
    result = repo.verify("requester", "repo", "Write")
    assert result["verified"] is True
    assert result["current"]["role"] == "Write"
    assert result["current"]["source"] == "github-team-membership"
    assert len(connection.writes) == 3


def test_unreadable_policy_blocks_approved_grant_before_any_write(repository, monkeypatch):
    """사람 승인이 있어도 실행 시 권한표를 읽지 못하면 변경하지 않는다."""
    from unlockops.models import ToolFailure
    from unlockops import rules

    repo, connection, _ = repository

    def unavailable(*args):
        raise ToolFailure("INVALID_ACCESS_MATRIX", "invalid policy")

    monkeypatch.setattr(rules, "_section", unavailable)
    with pytest.raises(ToolFailure, match="invalid policy"):
        repo.grant("problem", "execution-key")
    assert connection.writes == []
