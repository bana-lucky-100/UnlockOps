from unlockops.models import Result, Status


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
