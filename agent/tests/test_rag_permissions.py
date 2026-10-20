"""기존 RAG 원문을 바꿨을 때 권한 상한과 근거 검증이 함께 바뀌는지 검사한다."""

from pathlib import Path
import shutil

import pytest

from unlockops import rules
from unlockops.models import ToolFailure
from unlockops.settings import settings
from dataclasses import replace
from unlockops_rag.search import DocumentIndex


DATA = Path(__file__).resolve().parents[2] / "data"
PROFILE = {"id": "requester", "department_id": "dev", "job_family": "DEV",
           "job_grade": "사원", "head_id": "head"}
RESOURCE = {"platform": "GITHUB", "access_scope": "TF"}
MEMBERSHIP = {"member": True, "leader_id": "leader"}
BUDGET = {"remaining_monthly_amount": "150", "unit_monthly_price": "19"}


@pytest.mark.parametrize("platform,scope,family,grade,expected", [
    ("GITHUB", "GENERAL", "DEV", "사원", "Read"),
    ("GITHUB", "GENERAL", "DEV", "대리", "Write"),
    ("GITHUB", "TF", "DEV", "사원", "Write"),
    ("GITHUB", "TF", "NON_DEV", "부장", "Read"),
    ("GITHUB", "SEAT", "DEV", "사원", "Seat"),
    ("GITHUB", "SEAT", "NON_DEV", "부장", ""),
    ("JIRA", "GENERAL", "DEV", "사원", "Viewer"),
    ("JIRA", "GENERAL", "DEV", "대리", "Developer"),
    ("JIRA", "TF", "DEV", "사원", "Developer"),
    ("SLACK", "TF", "NON_DEV", "사원", "Member"),
    ("NOTION", "DEPARTMENT", "NON_DEV", "대리", "Can edit"),
    ("NOTION", "TF", "DEV", "부장", "Can view"),
])
def test_company_access_ceilings(platform, scope, family, grade, expected):
    """회사 권한표의 행·열을 직원 직무·직급에 맞춰 읽는지 확인한다."""
    profile = {**PROFILE, "job_family": family, "job_grade": grade}
    resource = {"platform": platform, "access_scope": scope}
    assert rules.ceiling(profile, resource) == expected


@pytest.mark.parametrize("resource,membership,current,budget,role,status,code", [
    (RESOURCE, MEMBERSHIP, {}, None, "Admin", "REJECTED", "FORBIDDEN_ADMIN"),
    (RESOURCE, {"member": False}, {}, None, "Write", "REJECTED", "NOT_TF_MEMBER"),
    ({"platform": "NOTION", "access_scope": "CONFIDENTIAL", "security_grade": "CONFIDENTIAL", "designated_department_id": "hr"},
     {}, {}, None, "Can view", "REJECTED", "CONFIDENTIAL_DEPARTMENT"),
    ({"platform": "NOTION", "access_scope": "DEPARTMENT", "owner_department_id": "hr"},
     {}, {}, None, "Can view", "REJECTED", "DEPARTMENT_MISMATCH"),
    ({"platform": "GITHUB", "access_scope": "SEAT"}, {}, {"role": "Seat"}, BUDGET,
     "Seat", "REJECTED", "DUPLICATE_SEAT"),
    ({"platform": "GITHUB", "access_scope": "SEAT"}, {}, {}, None,
     "Seat", "MANUAL_REVIEW", "BUDGET_UNAVAILABLE"),
    ({"platform": "GITHUB", "access_scope": "SEAT"}, {}, {}, BUDGET,
     "Read", "REJECTED", "ABOVE_ACCESS_CEILING"),
    ({"platform": "JIRA", "access_scope": "TF"}, MEMBERSHIP,
     {"role": "Developer", "can_browse": False}, None, "Developer", "MANUAL_REVIEW", "JIRA_SCHEME_MISMATCH"),
    (RESOURCE, MEMBERSHIP, {"role": "Write"}, None, "Read", "DONE", "ALREADY_HAS_ACCESS"),
    (RESOURCE, {"member": True, "leader_id": "requester"}, {}, None,
     "Write", "MANUAL_REVIEW", "APPROVER_UNAVAILABLE"),
])
def test_policy_rejections_and_manual_review(resource, membership, current, budget, role, status, code):
    """금지 권한·소속 불일치·좌석 중복 등 상황별 상태와 사유 코드가 맞는지 확인한다."""
    result = rules.evaluate(PROFILE, resource, membership, current, budget, role)
    assert (result.status, result.code) == (status, code)


@pytest.mark.parametrize("remaining,price,status", [
    ("18.99", "19.00", "REJECTED"),
    ("19.00", "19.00", "WAITING_APPROVAL"),
    ("9007199254740992.00", "9007199254740992.01", "REJECTED"),
])
def test_budget_uses_exact_decimal_comparison(remaining, price, status):
    """가격과 같은 예산은 허용하고, 아주 작은 부족 금액도 반올림으로 놓치지 않는지 확인한다."""
    budget = {"remaining_monthly_amount": remaining, "unit_monthly_price": price}
    result = rules.evaluate(PROFILE, {"platform": "GITHUB", "access_scope": "SEAT"}, {}, {}, budget)
    assert result.status == status


def copy_sources(tmp_path, monkeypatch):
    """테스트용 규정 사본과 데이터 경로를 준비한다. 실제 원문은 바꾸지 않는다."""
    for name in ("company-a-access-matrix.md", "policy_corpus.md"):
        shutil.copyfile(DATA / name, tmp_path / name)
    monkeypatch.setattr(rules, "settings", replace(settings, data_dir=tmp_path))
    return tmp_path / "company-a-access-matrix.md"


def test_existing_markdown_change_updates_lookup_and_execution_check(tmp_path, monkeypatch):
    """별도 설정 없이 기존 권한표의 셀 변경만으로 상한 조회와 실행 검증이 바뀌는지 확인한다."""
    matrix = copy_sources(tmp_path, monkeypatch)
    matrix.write_text(matrix.read_text(encoding="utf-8").replace(
        "| GitHub | TF 전용 저장소 (TF 구성원만) | Write | Write | Read |",
        "| GitHub | TF 전용 저장소 (TF 구성원만) | Read | Write | Read |",
    ), encoding="utf-8")
    assert rules.ceiling(PROFILE, RESOURCE) == "Read"
    result = rules.evaluate(PROFILE, RESOURCE, MEMBERSHIP, {}, None, "Write")
    assert (result.status, result.code) == ("REJECTED", "ABOVE_ACCESS_CEILING")


@pytest.mark.parametrize("change", ["missing_row", "duplicate_row", "unknown_role"])
def test_unreadable_matrix_does_not_guess_a_permission(tmp_path, monkeypatch, change):
    """적용 행이 없거나 중복되거나 역할을 읽을 수 없을 때 권한을 추측하지 않는지 확인한다."""
    matrix = copy_sources(tmp_path, monkeypatch)
    source = matrix.read_text(encoding="utf-8")
    row = "| GitHub | TF 전용 저장소 (TF 구성원만) | Write | Write | Read |"
    replacement = {"missing_row": "", "duplicate_row": row + "\n" + row,
                   "unknown_role": row.replace("Write", "Unknown")}[change]
    matrix.write_text(source.replace(row, replacement), encoding="utf-8")
    with pytest.raises(ToolFailure) as caught:
        rules.ceiling(PROFILE, RESOURCE)
    assert caught.value.code == "INVALID_ACCESS_MATRIX"


def test_missing_source_never_uses_an_old_permission(tmp_path, monkeypatch):
    """원문이 없을 때 예전 상한이나 기본 허용값을 대신 사용하지 않는지 확인한다."""
    copy_sources(tmp_path, monkeypatch)
    (tmp_path / "company-a-access-matrix.md").unlink()
    with pytest.raises(ToolFailure) as caught:
        rules.ceiling(PROFILE, RESOURCE)
    assert caught.value.code == "POLICY_SOURCE_UNAVAILABLE"


def test_source_edits_require_fresh_rag_evidence_without_another_policy_file(tmp_path, monkeypatch):
    """원문 변경 후에는 오래된 근거를 거절하고 다시 조회한 근거를 받아들이는지 확인한다."""
    matrix = copy_sources(tmp_path, monkeypatch)
    index = DocumentIndex(matrix, "business", {3, 4, 7})
    # 변경 전 청크는 이전 파일 해시를 갖고 있으므로, 파일이 바뀐 뒤에는 유효한 근거가 아니다.
    old_evidence = [chunk for doc in index.documents for chunk in index.read(doc)]
    old_hashes = rules.source_hashes()
    matrix.write_text(matrix.read_text(encoding="utf-8") + "\n새 문서 버전\n", encoding="utf-8")
    assert rules.source_hashes() != old_hashes
    assert rules.grounded_evidence(["A-ACCESS-03"], old_evidence) is None
    fresh_evidence = DocumentIndex(matrix, "business", {3, 4, 7}).read("A-ACCESS-03")
    assert rules.grounded_evidence(["A-ACCESS-03"], fresh_evidence)


def test_approver_grade_comes_from_existing_company_document(tmp_path, monkeypatch):
    """승인자 최소 직급도 코드의 고정 숫자가 아니라 7절 원문에서 읽는지 확인한다."""
    matrix = copy_sources(tmp_path, monkeypatch)
    matrix.write_text(matrix.read_text(encoding="utf-8").replace(
        "앱 역할이 APPROVER이고 직급이 과장 이상", "앱 역할이 APPROVER이고 직급이 대리 이상",
    ), encoding="utf-8")
    actor = {"id": "leader", "role": "APPROVER", "job_grade": "대리"}
    assert rules.approver_is_eligible(PROFILE, RESOURCE, MEMBERSHIP, actor)


@pytest.mark.parametrize("actor,allowed", [
    ({"id": "leader", "role": "APPROVER", "job_grade": "과장"}, True),
    ({"id": "head", "role": "APPROVER", "job_grade": "부장"}, False),
    ({"id": "leader", "role": "REQUESTER", "job_grade": "부장"}, False),
    ({"id": "leader", "role": "APPROVER", "job_grade": "대리"}, False),
    (None, False),
])
def test_execution_requires_the_designated_eligible_approver(actor, allowed):
    """다른 승인자·요청자 역할·직급 미달·없는 승인자는 실행을 허용하지 않는지 확인한다."""
    assert rules.approver_is_eligible(PROFILE, RESOURCE, MEMBERSHIP, actor) is allowed


def test_current_permissions_are_compared_only_within_the_resource_role_family():
    """같은 숫자 순위라도 플랫폼 역할이나 좌석 종류가 다르면 서로 대체할 수 없는지 확인한다."""
    assert rules.role_satisfies(RESOURCE, "Write", "Read") is True
    assert rules.role_satisfies(RESOURCE, "Developer", "Read") is False
    assert rules.role_satisfies({"platform": "GITHUB", "access_scope": "SEAT"}, "Read", "Seat") is False
