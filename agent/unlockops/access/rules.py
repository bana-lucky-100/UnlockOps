"""기존 회사 권한표를 직접 읽고, 승인·실행에 필요한 사실과 근거를 검증한다.

읽는 순서: 원문 읽기 → 표에서 상한·승인자 찾기 → RAG 근거 확인 → 실행 조건 검증.
LLM의 권한 제안은 permission_proposal.py에서 받고, 이 파일은 실제 부여 가능 여부를 확인한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import re

from ..common.models import ToolFailure
from ..common.settings import settings


# 숫자는 직급 순서와 같은 SaaS 안의 권한 포함 관계를 비교할 때만 사용한다.
# 예를 들어 Write 보유자는 Read 요청을 충족한다. 서로 다른 SaaS의 숫자는 비교하지 않는다.
# '개발 사원에게 어떤 권한을 줄 수 있는가'라는 회사별 상한은 아래 상수에 두지 않고 원문에서 읽는다.
GRADES = {"사원": 1, "대리": 2, "과장": 3, "차장": 4, "부장": 5}
ROLES = {"Read": 1, "Write": 2, "Viewer": 1, "Developer": 2,
         "Can view": 1, "Can edit": 2, "Member": 1, "Seat": 1}
FORBIDDEN = {"admin", "owner", "project admin", "full access", "전체 액세스"}
FAMILIES = {"GITHUB": {"Read", "Write"}, "JIRA": {"Viewer", "Developer"},
            "SLACK": {"Member"}, "NOTION": {"Can view", "Can edit"}}
# DB의 자원 종류를 권한표의 행 이름과 연결한다. 실제 허용 역할은 해당 행의 셀 값이다.
SCOPE_LABELS = {"GENERAL": "일반", "TF": "TF 전용", "SEAT": "유료 좌석",
                "DEPARTMENT": "부서 내부", "CONFIDENTIAL": "기밀"}
PLATFORM_POLICIES = {"GITHUB": "POL-03", "JIRA": "POL-04", "SLACK": "POL-05", "NOTION": "POL-08"}


@dataclass(frozen=True)
class Verdict:
    """판정 결과와 그 판정에 사용한 원문·청크 정보를 함께 전달한다."""
    status: str
    code: str
    message: str
    role: str = ""
    source_ids: tuple[str, ...] = ()  # 문서·절 ID: A-ACCESS-03, POL-02 등
    evidence_ids: tuple[str, ...] = ()  # 실제 조회한 세부 청크의 ID
    source_hashes: dict[str, str] = field(default_factory=dict)  # 파일 내용의 SHA-256


def _source(filename):
    """설정된 data 폴더에서 기존 규정 파일을 읽는다. 없으면 임의 기준으로 대체하지 않는다."""
    try:
        return (settings.data_dir / filename).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "권한 규정 원문을 확인할 수 없습니다.") from None


def source_hashes():
    """현재 원문의 지문을 만든다. 같은 문서 이름이어도 내용이 바뀌면 해시가 달라진다."""
    return {name: hashlib.sha256(_source(name).encode()).hexdigest()
            for name in ("company-a-access-matrix.md", "policy_corpus.md")}


def _section(number):
    """회사 권한표에서 '## 번호.' 제목부터 다음 번호 제목 직전까지 추출한다."""
    # (?m)은 줄마다 ^를 적용하고, (?s)는 줄바꿈까지 .으로 읽게 한다.
    match = re.search(rf"(?ms)^## {number}\.[^\n]*\n(.*?)(?=^## \d+\.|\Z)",
                      _source("company-a-access-matrix.md"))
    if not match:
        raise ToolFailure("INVALID_ACCESS_MATRIX", "회사 권한표의 필수 절을 확인할 수 없습니다.")
    return match.group(1)


def _table(text):
    """Markdown 표를 행·셀 목록으로 바꾸고 굵게 표시·코드 표시·구분 행을 제외한다."""
    # '| GitHub | 일반 저장소 | Read |'를 ['GitHub', '일반 저장소', 'Read']로 바꾼다.
    rows = [[re.sub(r"[*`]", "", cell).strip() for cell in line.strip().strip("|").split("|")]
            for line in text.splitlines() if line.strip().startswith("|")]
    return [row for row in rows if not all(re.fullmatch(r"[-:\s]+", cell) for cell in row)]


def _grade_match(text, grade):
    """'사원'은 해당 직급만, '대리 이상'은 대리부터 부장까지 선택한다."""
    found = re.search("|".join(GRADES), text)
    if not found:
        # '비개발(전 직급)'처럼 직급 조건이 없는 표기는 모든 직급에 적용한다.
        return True
    threshold = GRADES[found.group()]
    return grade >= threshold if "이상" in text else grade == threshold


def _role_cell(cell, grade):
    """셀에서 해당 직원에게 적용되는 역할 하나를 읽어 SaaS 역할 이름으로 맞춘다."""
    if cell == "신청 불가":
        return ""
    # 한 셀에 '사원 Can view, 대리 이상 Can edit'처럼 조건이 여러 개일 수 있다.
    parts = [part.strip() for part in cell.split(",")]
    matching = [part for part in parts if _grade_match(part, grade)]
    if len(matching) != 1:
        raise ToolFailure("INVALID_ACCESS_MATRIX", "직급별 권한 표기를 하나로 해석할 수 없습니다.")
    # 적용할 조건을 고른 뒤 '대리 이상' 같은 접두어를 제거해 역할 이름만 남긴다.
    value = re.sub(r"^(?:" + "|".join(GRADES) + r")(?:\s+이상)?\s+", "", matching[0])
    aliases = {"좌석": "Seat", "참여": "Member"}
    value = aliases.get(value, value)
    if value not in ROLES:
        # 알 수 없는 설명이 붙으면 역할 일부만 추출해 허용하지 않고 검토를 요구한다.
        raise ToolFailure("INVALID_ACCESS_MATRIX", "회사 권한표의 역할 표기를 확인할 수 없습니다.")
    return value


def ceiling(profile, resource):
    """권한 상한은 기존 RAG 문서의 3절 표에서 직접 읽는다. 별도 정책 사본은 두지 않는다."""
    rows = _table(_section(3))
    grade = GRADES.get(profile["job_grade"])
    family = {"DEV": "개발", "NON_DEV": "비개발"}.get(profile["job_family"])
    scope = SCOPE_LABELS.get(resource["access_scope"])
    if grade is None or family is None or scope is None or not rows:
        raise ToolFailure("INVALID_ACCESS_MATRIX", "직원·자원과 권한표를 연결할 수 없습니다.")
    # 열은 직무·직급으로, 행은 플랫폼·자원 종류로 선택한다.
    # 예: 개발 사원 + GitHub TF 저장소 → 3절 표의 해당 셀에 적힌 Write.
    header_pattern = re.escape(family) + r"(?:\s+(?:" + "|".join(GRADES) + r")(?:\s+이상)?|\(전 직급\))"
    columns = [i for i, header in enumerate(rows[0][2:], 2)
               if re.fullmatch(header_pattern, header) and _grade_match(header, grade)]
    matches = [row for row in rows[1:] if len(row) == len(rows[0])
               and row[0].upper() == resource["platform"] and row[1].startswith(scope)]
    if len(columns) != 1 or len(matches) != 1:
        # 빠진 행이나 중복된 행 때문에 대상이 모호하면 넓은 권한을 추측하지 않는다.
        raise ToolFailure("INVALID_ACCESS_MATRIX", "회사 권한표에서 적용할 행·열을 확정할 수 없습니다.")
    return _role_cell(matches[0][columns[0]], grade)


def assigned_approver(profile, resource, membership):
    """7절의 승인자 표를 확인한 뒤 실제 조회한 TF 리더 또는 부서장 ID를 선택한다."""
    rows = _table(_section(7))
    tf = resource["access_scope"] == "TF"
    rows = [row for row in rows if len(row) == 2 and
            (row[0].startswith("TF 전용") if tf else row[0].startswith("일반·"))]
    expected = "리더" if tf else "부서장"
    if len(rows) != 1 or expected not in rows[0][1]:
        raise ToolFailure("INVALID_ACCESS_MATRIX", "회사 권한표의 승인자 기준을 확인할 수 없습니다.")
    return membership.get("leader_id") if tf else profile.get("head_id")


def approver_is_eligible(profile, resource, membership, actor):
    """실행 직전 지정 승인자의 ID·앱 역할·최소 직급과 본인 승인 금지를 검사한다."""
    # 최소 직급도 숫자로 고정하지 않고 7절의 '과장 이상' 문장에서 읽는다.
    match = re.search(r"승인자는 앱 역할이 ([A-Z_]+)이고 직급이 (" + "|".join(GRADES) + r") 이상", _section(7))
    if not match:
        raise ToolFailure("INVALID_ACCESS_MATRIX", "승인자의 역할·직급 기준을 확인할 수 없습니다.")
    expected = assigned_approver(profile, resource, membership)
    return bool(actor) and all((bool(expected), str(expected) == str(actor.get("id")),
        str(actor.get("id")) != str(profile["id"]), actor.get("role") == match.group(1),
        GRADES.get(actor.get("job_grade"), 0) >= GRADES[match.group(2)]))


def _family(resource):
    """역할을 비교할 범위를 정한다. Copilot 좌석은 저장소 Read/Write와 따로 취급한다."""
    return {"Seat"} if resource["access_scope"] == "SEAT" else FAMILIES.get(resource["platform"], set())


def role_satisfies(resource, held_role, requested_role):
    """같은 역할군 안에서 현재 권한이 요청 권한 이상인지 확인한다."""
    family = _family(resource)
    return held_role in family and requested_role in family and ROLES[held_role] >= ROLES[requested_role]


def required_sources(resource):
    """이 요청에서 반드시 확인할 회사 권한표와 플랫폼·자원별 규정 ID를 모은다."""
    sources = ["A-ACCESS-03", "A-ACCESS-04", "A-ACCESS-07", PLATFORM_POLICIES[resource["platform"]]]
    sources.extend({"TF": ["POL-02"], "SEAT": ["POL-06"]}.get(resource["access_scope"], []))
    return tuple(sources)


def grounded_evidence(sources, evidence):
    """필수 규정마다 현재 원문과 해시가 같은 청크를 찾고, 없으면 None을 반환한다."""
    if not isinstance(evidence, list) or any(not isinstance(chunk, dict) for chunk in evidence):
        return None
    hashes = source_hashes()
    selected = []
    for doc_id in sources:
        # 문서 ID가 속한 원본 파일을 찾고, 이름·해시·본문이 있는 근거만 사용한다.
        filename = "company-a-access-matrix.md" if doc_id.startswith("A-ACCESS-") else "policy_corpus.md"
        chunks = [chunk for chunk in evidence if all((chunk.get("doc_id") == doc_id,
            chunk.get("source") == filename, chunk.get("source_hash") == hashes[filename],
            bool(chunk.get("chunk_id")), bool(chunk.get("text"))))]
        if not chunks:
            return None
        selected.extend(chunk["chunk_id"] for chunk in chunks)
    return tuple(dict.fromkeys(selected))  # 검색과 원문 조회에서 중복된 청크 ID를 한 번만 남긴다.


def _budget_insufficient(budget):
    """소수점 금액을 Decimal로 비교한다. 큰 금액도 float 반올림으로 판정이 바뀌지 않게 한다."""
    if budget is None:
        return False
    try:
        remaining, price = (Decimal(str(budget[key])) for key in ("remaining_monthly_amount", "unit_monthly_price"))
        if not remaining.is_finite() or not price.is_finite() or price <= 0:
            raise ValueError("Invalid budget")
        return remaining < price
    except (InvalidOperation, ValueError, KeyError):
        raise ToolFailure("INVALID_POLICY_FACTS", "예산 정보를 확인할 수 없습니다.") from None


def evaluate(profile, resource, membership, current, budget, requested_role="", *, evidence=None):
    """문서의 상한과 실제 자격을 검증한다. LLM 모드는 제안된 역할을 검증할 때 호출한다."""
    sources = required_sources(resource)
    hashes = source_hashes()
    # Agent와 MCP 실행 경로는 근거를 전달한다. None은 내부에서 사실·상한만 비교할 때 사용한다.
    citations = grounded_evidence(sources, evidence) if evidence is not None else ()
    if citations is None:
        return Verdict("MANUAL_REVIEW", "POLICY_EVIDENCE_MISMATCH",
                       "현재 규정과 검색 근거의 원문 버전이 일치하지 않아 담당자 검토가 필요합니다.")
    # 허용 상한은 원문 표에서 읽고, 제안 역할은 그 상한을 넘지 못하게 한다.
    upper = ceiling(profile, resource)
    role = requested_role or ("Can view" if resource["platform"] == "NOTION" else upper)
    tf, seat = resource["access_scope"] == "TF", resource["access_scope"] == "SEAT"
    department = str(profile["department_id"])
    approver = assigned_approver(profile, resource, membership)
    # 각 항목: (해당 여부, 상태, 사유 코드, 안내 문장).
    # 목록은 반환 우선순위다. 아래에서 처음 해당하는 항목 하나를 최종 판정으로 선택한다.
    checks = [
        # 금지 권한과 실제 소속·보안 범위 확인.
        (role.lower() in FORBIDDEN, "REJECTED", "FORBIDDEN_ADMIN", "Admin·Owner·전체 액세스는 IT 보안팀의 별도 절차로 처리해야 합니다."),
        (tf and not membership.get("member"), "REJECTED", "NOT_TF_MEMBER", "TF 명단에 없습니다. TF 리더에게 구성원 등재를 요청해야 합니다."),
        (resource.get("security_grade") == "CONFIDENTIAL" and department != str(resource.get("designated_department_id")),
         "REJECTED", "CONFIDENTIAL_DEPARTMENT", "기밀 문서의 지정 부서가 아닙니다. 부서장에게 문의해야 합니다."),
        (resource["access_scope"] == "DEPARTMENT" and department != str(resource.get("owner_department_id")),
         "REJECTED", "DEPARTMENT_MISMATCH", "소속 부서 전용 문서가 아닙니다."),
        # 유료 좌석의 중복·신청 자격·예산 확인.
        (seat and bool(current.get("role")), "REJECTED", "DUPLICATE_SEAT", "이미 Copilot 좌석을 보유하고 있습니다."),
        (seat and not upper, "REJECTED", "NON_DEV_SEAT", "유료 개발 도구 좌석은 개발 직무만 신청할 수 있습니다."),
        (seat and budget is None, "MANUAL_REVIEW", "BUDGET_UNAVAILABLE", "부서 예산을 확인할 수 없어 담당자 검토가 필요합니다."),
        (seat and _budget_insufficient(budget), "REJECTED", "BUDGET_INSUFFICIENT", "부서 잔여 예산이 좌석 가격보다 적습니다. 부서장에게 예산 증액을 요청해야 합니다."),
        # 지원하는 역할인지, 원문 상한 이내인지, 자동 처리 범위인지 확인.
        (not upper or role not in ROLES, "MANUAL_REVIEW", "UNSUPPORTED_ROLE", "자동 처리 근거가 없는 역할입니다. 담당자 검토가 필요합니다."),
        (role not in _family(resource) or ROLES.get(role, 0) > ROLES.get(upper, 0),
         "REJECTED", "ABOVE_ACCESS_CEILING", f"회사 권한표의 허용 상한은 {upper}입니다."),
        (resource["platform"] == "NOTION" and role == "Can edit", "MANUAL_REVIEW", "EDIT_OUT_OF_DEMO_SCOPE", "문서 편집 권한은 이번 자동 부여 범위 밖입니다."),
        (resource["platform"] == "JIRA" and bool(current.get("role")) and current.get("can_browse") is False,
         "MANUAL_REVIEW", "JIRA_SCHEME_MISMATCH", "프로젝트 역할은 있으나 조회 권한이 없습니다. 권한 스킴을 담당자가 확인해야 합니다."),
        # 이미 보유한 권한이면 변경 없이 완료하고, 나머지는 지정 승인자에게 넘긴다.
        (role_satisfies(resource, current.get("role"), role), "DONE", "ALREADY_HAS_ACCESS", "조회 결과 필요한 권한을 이미 보유하고 있습니다."),
        (not approver or str(approver) == str(profile["id"]), "MANUAL_REVIEW", "APPROVER_UNAVAILABLE", "유효한 승인자를 지정할 수 없습니다. 본인 승인은 허용하지 않습니다."),
        (True, "WAITING_APPROVAL", "ELIGIBLE", f"{role} 부여 조건을 충족합니다. 지정 승인자의 승인이 필요합니다."),
    ]
    _, status, code, message = next(check for check in checks if check[0])
    return Verdict(status, code, message, role if status in {"DONE", "WAITING_APPROVAL"} else "",
                   sources, citations, hashes)
