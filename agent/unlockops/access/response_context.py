"""Prepare checked workflow facts and bound policy excerpts for user guidance."""
import hashlib

WRITING_GUIDE = [
    "확인한 사실 → 판단 이유 → 사용자가 할 다음 행동 순서로 한국어 안내를 작성한다.",
    "조회 사실과 문서의 일반 규정을 구분한다. null은 미확인이며 자격 미달로 단정하지 않는다.",
    "직원의 소속·권한·예산을 문서 예시에서 추측하지 않는다.",
    "권한 변경은 사람의 승인과 서버 실행이 필요하며, 안내가 승인·변경 완료를 뜻하지 않는다.",
    "각 안내 단계에 관련 문서의 인용 ID와 원문 발췌를 붙인다. 근거가 부족하면 답변 불가로 반환한다.",
]


def source_id(evidence):
    return evidence["doc_id"] + ":" + hashlib.sha256(evidence["article"].encode()).hexdigest()[:16]


def select_sources(state):
    platform = state["context"]["problem"]["platform"]
    selected = []
    for evidence in state.get("guidance_evidence", state.get("evidence", [])):
        fields = evidence["article"].split(" | ")
        if len(fields) == 4 and fields[1] not in {"COMMON", platform}:
            continue
        selected.append({**evidence, "chunk_id": source_id(evidence), "platform": platform,
                         "source": evidence["doc_id"]})
    return selected[:8]


def build_response_context(state):
    context, assessment = state["context"], state["assessment"]
    option = next((e for e in context["entitlements"] if e["id"] == state.get("entitlement_id")), None)
    checked = assessment["reason"] == "ALREADY_HAS_ACCESS"
    facts = {"current_permissions_checked": checked,
             "current_role": option["code"] if checked and option else None}
    if assessment.get("review_facts"):
        facts.update({k: assessment["review_facts"][k] for k in ("access_scope", "tf_member")})
    return {"question": context["problem"]["contents"], "platform": context["problem"]["platform"],
            "request_type": state["intent"]["request_type"], "resource": option["name"] if option else None,
            "facts": facts, "decision": {"handling": "ANSWER", "status": "DONE",
                "reason_code": assessment["reason"], "diagnosis": assessment["message"]},
            "sources": select_sources(state), "writing_guide": list(WRITING_GUIDE)}
