"""Approval narration uses explicit observations, never examples in the retrieved policy."""
from decimal import Decimal
from importlib.resources import files

from unlockops_rag.approval import source_role


def review_guidance():
    return files("unlockops.access").joinpath("approval-review-guide.md").read_text(encoding="utf-8")


def review_input(state):
    assessment = state["assessment"]
    context = state["context"]
    requester = context["requester"]
    plan = assessment.get("plan")
    observed = assessment.get("review_facts")
    selected = next((e for e in context["entitlements"] if e["id"] == state.get("entitlement_id")), None)
    facts = {
        "server_assessment": {k: assessment[k] for k in ("status", "reason", "message")},
        "platform": context["problem"]["platform"],
        "requester": {k: requester[k] for k in ("employment_status", "job_family", "job_grade")},
        "account_observations": [
            {k: f.get(k) for k in ("account_exists", "license_active", "data_access", "work_scope_assigned", "job_function", "observed_at")}
            for f in context["facts"]
        ],
        "review_facts": observed,
        "least_privilege_proposed": bool(state.get("least_privilege")),
        "source_roles": [{"article": e["article"], "role": source_role(e["article"])} for e in state["evidence"]],
    }
    lines = [assessment["message"]]
    lines.append(f"확인 사실: 재직 상태 {requester['employment_status']}, 직무 {requester['job_family']}, 직급 {requester['job_grade']}. 직급만으로 권한·승인자를 정하지 않습니다.")
    for observation in facts["account_observations"]:
        labels = {True: "확인", False: "미충족", None: "미확인"}
        lines.append("계정 관측: " + ", ".join(
            f"{label} {labels[observation[key]]}" for key, label in (
                ("account_exists", "계정"), ("license_active", "기본 라이선스"),
                ("work_scope_assigned", "업무 배정"), ("data_access", "데이터 접근")
            )
        ) + f". 관측 시각: {observation['observed_at'] or '미전달'}.")
    if selected:
        facts["proposed_entitlement"] = {k: selected[k] for k in ("code", "kind", "name")}
        lines.append(f"검토 대상: {selected['name']} / {selected['code']}.")
    if state.get("least_privilege"):
        # Selection permits this only for GitHub code reading, with no modification purpose.
        lines.append("상위 관리자 권한 요청에 대해 코드 열람에 필요한 Read만 제안합니다. 쓰기·설정 변경 권한은 포함하지 않습니다.")
    if observed:
        facts["projected_budget"] = format(Decimal(observed["remaining_budget"]) - Decimal(observed["monthly_amount"]), ".2f")
        if observed["tf_member"] is True:
            lines.append("서버에서 대상 TF 구성원 자격을 확인했습니다.")
        amount, currency = observed["monthly_amount"], observed["currency"]
        basis = plan["cost_basis"] if plan else "서버 예상 비용"
        labels = {"SEAT_MONTHLY": "월 좌석 비용", "USAGE_ESTIMATE": "월 사용량 예상 비용", "NO_ADDITIONAL_COST": "추가 비용"}
        lines.append(f"{labels.get(basis, basis)}: {amount} {currency}. 예산 검토: {observed['remaining_budget']} → {facts['projected_budget']} {currency} (실제 차감 전).")
        source = {"SYNTHETIC_CONTRACT": "시연 가정", "PUBLIC_LIST_PRICE": "제공 자료의 정가 기록", "CONTRACT": "계약 근거"}[observed["price_source_kind"]]
        lines.append(f"단가 출처: {source}. 확인 시각: {observed['checked_at']}.")
    elif plan:
        lines.append(f"예상 월 비용: {plan['monthly_amount']} {plan['currency']}. 잔여 예산의 개별 조회 값은 전달되지 않았습니다.")
    if plan:
        facts["plan"] = {k: plan[k] for k in ("monthly_amount", "currency", "cost_basis")}
        facts["plan"]["total_steps"] = len(plan["approver_ids"])
        lines.append(f"총 {len(plan['approver_ids'])}단계의 순차 승인이 필요합니다. 1차 담당자는 업무 필요성을, 이후 담당자는 규정·허용 범위·비용과 앞선 검토 기록을 확인해 주세요.")
        if plan["cost_basis"] == "USAGE_ESTIMATE":
            lines.append("사용량 비용은 예상값이며 실제 청구액이 아닙니다.")
        lines.append("최초 분석 시점의 검토 자료이며, 승인·실행 전에 서버가 최신 조건을 다시 확인합니다. 아직 권한은 변경되지 않았습니다.")
    elif assessment["reason"] == "BUDGET_INSUFFICIENT":
        lines.append("예산 확보 후 최신 정책·예산으로 재검토해 주세요. 아직 권한은 변경되지 않았습니다.")
    # Keep the source labels visible even when the model is unavailable.
    articles = [e["article"] for e in state["evidence"] if source_role(e["article"]) in {"COMPANY_POLICY", "COMPANY_WORKFLOW"}]
    if articles:
        lines.append("검토 근거: " + "; ".join(articles[:5]) + ".")
    return facts, "\n".join(lines)
