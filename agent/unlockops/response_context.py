"""조회 사실·확정 판정·문서 근거를 답변 작성용 입력으로 정리한다. 외부 호출은 하지 않는다."""

from decimal import Decimal, InvalidOperation


WRITING_GUIDE = [
    "확인한 사실 → 판단 이유 → 사용자가 할 다음 행동 순서로 한국어 안내를 작성한다.",
    "확정된 decision의 처리 경로·상태·요청 역할을 바꾸거나 승인·변경 완료를 만들어 내지 않는다.",
    "조회 사실과 문서의 일반 규정을 구분한다. null은 미확인이며 false나 자격 미달로 단정하지 않는다.",
    "current_permissions_checked=true이고 current_role=null이면 조회 결과 보유 권한이 없는 것이다.",
    "maximum_role의 빈 문자열은 허용 역할 없음이며, null은 상한 미확인이다.",
    "권한 상한은 부여 자격의 한 기준이며 TF 소속·부서·예산·승인을 대신하지 않는다.",
    "문서의 초안·미확정 예외를 확정 정책으로 설명하지 않는다. 코드의 판정과 충돌하면 판정을 우선한다.",
    "각 안내 단계에 관련 문서의 인용 ID와 원문 발췌를 붙인다. 근거가 부족하면 답변 불가로 반환한다.",
]


def select_sources(state):
    """검색 안내 최대 5개와 회사 규정 3·4·7절의 관련 청크를 각 1개씩 선택한다."""
    platform = state["job"]["platform"]
    prefix = {"GITHUB": "GH", "JIRA": "JR", "SLACK": "SL", "NOTION": "NT"}[platform]
    policy_ids = {"POL-01", "POL-02", "POL-07", {
        "GITHUB": "POL-03", "JIRA": "POL-04", "SLACK": "POL-05", "NOTION": "POL-08",
    }[platform]}
    if platform == "GITHUB":
        policy_ids.add("POL-06")
    policies, company = {}, {}
    for chunk in state.get("answer_sources", []):
        doc_id = chunk.get("doc_id", "")
        if (doc_id in policy_ids or doc_id.startswith(prefix + "-OFF-")) and chunk.get("chunk_id") and chunk.get("text", "").strip():
            policies[chunk["chunk_id"]] = chunk
    resource, profile = state.get("resource", {}), state.get("profile", {})
    terms = [platform.casefold(), profile.get("job_grade", ""), {
        "TF": "TF", "SEAT": "좌석", "DEPARTMENT": "부서", "CONFIDENTIAL": "기밀",
    }.get(resource.get("access_scope"), "일반")]
    for doc_id in ("A-ACCESS-03", "A-ACCESS-04", "A-ACCESS-07"):
        candidates = [c for c in state.get("evidence", []) if resource and c.get("doc_id") == doc_id
                      and c.get("chunk_id") and c.get("text", "").strip()]
        if candidates:
            company[doc_id] = max(candidates, key=lambda c: sum(
                bool(term) and term.casefold() in c["text"].casefold() for term in terms
            ))
    # 출처 정보는 보존하고, 도구 응답의 임의 추가 필드는 모델 입력에서 제외한다.
    metadata = ("chunk_id", "doc_id", "article", "platform", "source", "version", "source_hash")
    selected = [*list(policies.values())[:5], *company.values()]
    return [{**{key: c[key] for key in metadata if key in c}, "text": c["text"][:5000]} for c in selected]


def budget_sufficient(budget):
    """금액 원문 대신 비교 결과만 전달하고 미확인 값은 None으로 남긴다."""
    if not budget:
        return None
    try:
        balance = Decimal(budget["remaining_monthly_amount"])
        price = Decimal(budget["unit_monthly_price"])
        return balance >= price if balance.is_finite() and price.is_finite() and price > 0 else None
    except (KeyError, InvalidOperation, ValueError, TypeError):
        return None


def department_match(profile, resource, key):
    """부서 ID를 노출하지 않고 일치 여부만 전달한다."""
    actual, expected = profile.get("department_id"), resource.get(key)
    return str(actual) == str(expected) if actual is not None and expected is not None else None


def build_response_context(state):
    """기존 체크포인트도 읽고, 답변에 필요한 사실만 허용 목록으로 복사한다."""
    profile, resource = state.get("profile", {}), state.get("resource", {})
    current, result = state.get("current", {}), state["result"]
    intent, plan = state.get("intent", {}), state.get("plan") or {}
    # 이전 체크포인트에는 상한이 evidence에만 있으므로 그 조회 사실을 재사용한다.
    previous = next((e for e in state.get("evidence", []) if e.get("kind") == "employee_facts"), {})
    facts = {
        "resource_resolved": bool(resource),
        "current_permissions_checked": "role" in current,
        "current_role": current.get("role"),
        "maximum_role": state.get("maximum_role", previous.get("maximum_role")),
        "job_grade": profile.get("job_grade"),
        "job_family": profile.get("job_family"),
    }
    if resource.get("access_scope") == "TF":
        facts["tf_member"] = state.get("membership", {}).get("member")
    if resource.get("access_scope") == "SEAT":
        facts["budget_sufficient"] = budget_sufficient(state.get("budget"))
    if resource.get("access_scope") == "DEPARTMENT":
        facts["owner_department_matches"] = department_match(profile, resource, "owner_department_id")
    if resource.get("security_grade") == "CONFIDENTIAL":
        facts["designated_department_matches"] = department_match(profile, resource, "designated_department_id")
    if state["job"]["platform"] == "JIRA":
        facts["can_browse"] = current.get("can_browse")
    return {
        "question": state["job"]["contents"],
        "platform": state["job"]["platform"],
        "request_type": intent.get("request_type", "TROUBLESHOOT"),
        "resource": resource.get("name"),
        "access_scope": resource.get("access_scope"),
        "facts": facts,
        "decision": {
            "handling": state.get("handling"), "status": result.get("status"),
            "reason_code": result.get("reasonCode"), "diagnosis": result.get("diagnosis"),
            "requested_role": plan.get("requested_role") or intent.get("requested_role") or None,
            "verification_ok": result.get("verification_ok"), "next_action": result.get("nextAction"),
        },
        "sources": select_sources(state),
        "writing_guide": list(WRITING_GUIDE),
    }
