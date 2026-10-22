from unlockops.common.models import Result, Status


def test_old_checkpoint_budget_result_is_safe_to_republish():
    saved = dict(status="ON_HOLD", reasonCode="INSUFFICIENT_BUDGET", summary="old summary",
                 diagnosis="original cause", proposal="original proposal", nextAction="예산 증액 요청")
    result = Result.model_validate(saved).model_dump(mode="json")
    assert result["status"] == "REJECTED"
    assert result["reasonCode"] == "BUDGET_INSUFFICIENT"
    assert result["diagnosis"] == saved["diagnosis"]
    assert result["proposal"] == saved["proposal"]
    assert saved["status"] == "ON_HOLD"
    assert len(Status) == 8


def test_legacy_guidance_normalizes_without_mutating_checkpoint():
    saved = dict(status="MANUAL_REVIEW", reasonCode="RAG_GUIDANCE", summary="안내",
                 diagnosis="권한 보유", proposal="점검 안내", nextAction="확인")
    result = Result.model_validate(saved)
    assert result.status == "DONE" and result.result_type == "GUIDANCE"
    assert result.verification_ok is None and result.plan is None
    assert saved["status"] == "MANUAL_REVIEW"


def test_empty_legacy_guidance_remains_manual_review():
    result = Result(status="MANUAL_REVIEW", reasonCode="RAG_GUIDANCE", summary="",
                    diagnosis="", proposal="  ", nextAction="")
    assert result.status == "MANUAL_REVIEW" and result.result_type is None


def test_completion_requires_explicit_valid_semantics():
    import pytest
    from pydantic import ValidationError
    base = dict(status="DONE", reasonCode="TEST", summary="", diagnosis="", proposal="안내", nextAction="")
    with pytest.raises(ValidationError):
        Result(**base)
    with pytest.raises(ValidationError):
        Result(**base, result_type="GUIDANCE", verification_ok=True)
    with pytest.raises(ValidationError):
        Result(**base, result_type="ACCESS_VERIFIED", verification_ok=False)
    with pytest.raises(ValidationError):
        Result(**{**base, "status": "MANUAL_REVIEW"}, result_type="GUIDANCE")
    legacy = Result(**base, verification_ok=True)
    assert legacy.result_type == "ACCESS_VERIFIED"
