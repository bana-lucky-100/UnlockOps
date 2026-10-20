"""직무·직급·소속 규칙으로 판정한다. 모델의 설명 문장만으로는 부여하지 않는다."""

from __future__ import annotations

from dataclasses import dataclass

# 회사 직급과 SaaS 역할은 서로 다른 기준이다.
GRADES = {"사원": 1, "대리": 2, "과장": 3, "차장": 4, "부장": 5}
ROLES = {
    "Read": 1,
    "Write": 2,
    "Viewer": 1,
    "Developer": 2,
    "Can view": 1,
    "Can edit": 2,
    "Member": 1,
    "Seat": 1,
}
FORBIDDEN = {"admin", "owner", "project admin", "full access", "전체 액세스"}


@dataclass(frozen=True)
class Verdict:
    status: str
    code: str
    message: str
    role: str = ""


def ceiling(profile, resource):
    """직무·직급·자원 종류로 받을 수 있는 역할의 상한을 구한다."""
    dev = profile["job_family"] == "DEV"
    senior = GRADES.get(profile["job_grade"], 0) >= 2
    platform, scope = resource["platform"], resource["access_scope"]
    if scope == "SEAT":
        return "Seat" if dev else ""
    if platform == "GITHUB":
        return "Write" if dev and (scope == "TF" or senior) else "Read"
    if platform == "JIRA":
        return "Developer" if dev and (scope == "TF" or senior) else "Viewer"
    if platform == "SLACK":
        return "Member"
    if platform == "NOTION":
        return "Can edit" if scope == "DEPARTMENT" and senior else "Can view"
    return ""


def evaluate(profile, resource, membership, current, budget, requested_role="") -> Verdict:
    """금지·자격·상한·현재 권한·승인자를 순서대로 확인한다."""
    role = requested_role or (
        "Can view" if resource["platform"] == "NOTION" else ceiling(profile, resource)
    )
    if role.lower() in FORBIDDEN:
        return Verdict(
            "REJECTED",
            "FORBIDDEN_ADMIN",
            "Admin·Owner·전체 액세스는 IT 보안팀의 별도 절차로 처리해야 합니다.",
        )
    if resource["access_scope"] == "TF" and not membership.get("member"):
        return Verdict(
            "REJECTED",
            "NOT_TF_MEMBER",
            "TF 명단에 없습니다. TF 리더에게 구성원 등재를 요청해야 합니다.",
        )
    department = str(profile["department_id"])
    if resource.get("security_grade") == "CONFIDENTIAL" and department != str(
        resource.get("designated_department_id")
    ):
        return Verdict(
            "REJECTED",
            "CONFIDENTIAL_DEPARTMENT",
            "기밀 문서의 지정 부서가 아닙니다. 부서장에게 문의해야 합니다.",
        )
    if resource["access_scope"] == "DEPARTMENT" and department != str(
        resource.get("owner_department_id")
    ):
        return Verdict("REJECTED", "DEPARTMENT_MISMATCH", "소속 부서 전용 문서가 아닙니다.")
    if resource["access_scope"] == "SEAT":
        if current.get("role"):
            return Verdict("REJECTED", "DUPLICATE_SEAT", "이미 Copilot 좌석을 보유하고 있습니다.")
        if profile["job_family"] != "DEV":
            return Verdict(
                "REJECTED", "NON_DEV_SEAT", "유료 개발 도구 좌석은 개발 직무만 신청할 수 있습니다."
            )
        if budget is None:
            return Verdict(
                "MANUAL_REVIEW",
                "BUDGET_UNAVAILABLE",
                "부서 예산을 확인할 수 없어 담당자 검토가 필요합니다.",
            )
        if float(budget["remaining_monthly_amount"]) < float(budget["unit_monthly_price"]):
            return Verdict(
                "REJECTED",
                "BUDGET_INSUFFICIENT",
                "부서 잔여 예산이 좌석 가격보다 적습니다. 부서장에게 예산 증액을 요청해야 합니다.",
            )
    upper = ceiling(profile, resource)
    if not upper or role not in ROLES:
        return Verdict(
            "MANUAL_REVIEW",
            "UNSUPPORTED_ROLE",
            "자동 처리 근거가 없는 역할입니다. 담당자 검토가 필요합니다.",
        )
    same_family = {
        "GITHUB": {"Read", "Write", "Seat"}
        if resource["access_scope"] == "SEAT"
        else {"Read", "Write"},
        "JIRA": {"Viewer", "Developer"},
        "SLACK": {"Member"},
        "NOTION": {"Can view", "Can edit"},
    }[resource["platform"]]
    if role not in same_family or ROLES[role] > ROLES[upper]:
        return Verdict(
            "REJECTED", "ABOVE_ACCESS_CEILING", f"직무·직급·자원 기준의 허용 상한은 {upper}입니다."
        )
    if resource["platform"] == "NOTION" and role == "Can edit":
        return Verdict(
            "MANUAL_REVIEW",
            "EDIT_OUT_OF_DEMO_SCOPE",
            "문서 편집 권한은 이번 자동 부여 범위 밖입니다.",
        )
    held = current.get("role")
    if resource["platform"] == "JIRA" and held and current.get("can_browse") is False:
        return Verdict(
            "MANUAL_REVIEW",
            "JIRA_SCHEME_MISMATCH",
            "프로젝트 역할은 있으나 조회 권한이 없습니다. 권한 스킴을 담당자가 확인해야 합니다.",
        )
    if held and held in same_family and ROLES.get(held, 0) >= ROLES[role]:
        return Verdict(
            "DONE", "ALREADY_HAS_ACCESS", "조회 결과 필요한 권한을 이미 보유하고 있습니다.", role
        )
    approver = (
        membership.get("leader_id") if resource["access_scope"] == "TF" else profile.get("head_id")
    )
    if not approver or str(approver) == str(profile["id"]):
        return Verdict(
            "MANUAL_REVIEW",
            "APPROVER_UNAVAILABLE",
            "유효한 승인자를 지정할 수 없습니다. 본인 승인은 허용하지 않습니다.",
        )
    return Verdict(
        "WAITING_APPROVAL",
        "ELIGIBLE",
        f"{role} 부여 조건을 충족합니다. 지정 승인자의 승인이 필요합니다.",
        role,
    )
