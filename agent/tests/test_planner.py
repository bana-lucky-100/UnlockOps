"""요청 해석과 LLM 연결 재사용을 검사한다. 실제 모델 API는 호출하지 않는다."""

from dataclasses import replace

import pytest

from unlockops.access import planner
from pydantic import ValidationError

from unlockops.common.models import Intent
from unlockops.access.planner import model, raw_intent


@pytest.mark.parametrize("contents,expected", [
    ("payment-core에서 git remote 설정은 어떻게 확인하나요?", "GUIDE"),
    ("payment-core push 방법 알려주세요", "GUIDE"),
    ("Write 권한 신청 절차를 설명해주세요", "GUIDE"),
    ("How do I request access to payment-core?", "GUIDE"),
    ("payment-core에 push가 안 돼요", "TROUBLESHOOT"),
    ("Write 권한은 있는데 push할 때 403이 나요. 어떻게 해결해요?", "TROUBLESHOOT"),
    ("Copilot 좌석 신청했는데 오류가 나요", "TROUBLESHOOT"),
    ("PAY 권한 부여가 실패했어요", "TROUBLESHOOT"),
    ("payment-core Write 권한 주세요", "ACCESS_REQUEST"),
    ("Copilot 좌석 신청합니다", "ACCESS_REQUEST"),
    ("#proj-payment 채널에 초대해 주세요", "ACCESS_REQUEST"),
    ("403이 나요. payment-core 권한을 부여해 주세요", "ACCESS_REQUEST"),
    ("Please grant me Write access to payment-core", "ACCESS_REQUEST"),
])
def test_request_type_distinguishes_help_errors_and_explicit_access_requests(contents, expected):
    """권한 언급이나 '어떻게'만으로 신청·오류·사용법을 혼동하지 않는다."""
    assert raw_intent(contents).request_type == expected


def test_intent_reads_old_data_without_assuming_an_access_request():
    """분류 필드가 없는 이전 데이터는 권한 신청으로 단정하지 않는다."""
    assert Intent.model_validate({"symptom": "push 실패"}).request_type == "TROUBLESHOOT"
    with pytest.raises(ValidationError):
        Intent(request_type="PERMISSION_MISSING")


async def test_llm_request_type_is_not_overwritten_by_demo_role_heuristics(monkeypatch):
    """push나 권한 이름이 있어도 모델이 분류한 사용법 문의를 유지한다."""
    class FakeModel:
        def with_structured_output(self, schema):
            """실제 모델에 제공되는 구조화된 분류 스키마를 확인한다."""
            assert schema is Intent
            return self

        async def ainvoke(self, messages):
            """데모 규칙과 다른 문맥 해석을 모의 응답한다."""
            return Intent(request_type="GUIDE", resource_hint="payment-core")

    monkeypatch.setattr(planner, "settings", replace(planner.settings, mode="llm"))
    monkeypatch.setattr(planner, "model", FakeModel)
    intent = await planner.interpret("payment-core push 문의", "GITHUB")
    assert raw_intent("payment-core push 문의").request_type == "TROUBLESHOOT"
    assert intent.request_type == "GUIDE"


@pytest.mark.parametrize("word", ["README", "already", "thread", "spreadsheet", "rewrite"])
def test_role_substrings_are_not_explicit_roles(word):
    """다른 단어에 포함된 read와 write를 명시적 권한으로 해석하지 않는다."""
    assert raw_intent(f"{word} 작업이 안 돼요").requested_role == ""


@pytest.mark.parametrize("word", ["README", "already", "thread", "spreadsheet", "rewrite"])
def test_push_request_ignores_role_substrings(word):
    """문서 이름 등에 read가 있어도 push 요청은 Write로 해석한다."""
    assert raw_intent(f"{word} 수정을 push하려는데 안 돼요").requested_role == "Write"


@pytest.mark.parametrize(
    "token,role",
    [
        ("full access", "Full access"),
        ("admin", "Admin"),
        ("owner", "Owner"),
        ("can edit", "Can edit"),
        ("can view", "Can view"),
        ("maintain", "Maintain"),
        ("triage", "Triage"),
        ("write", "Write"),
        ("read", "Read"),
        ("developer", "Developer"),
        ("viewer", "Viewer"),
    ],
)
def test_explicit_roles_allow_punctuation_and_korean_suffix(token, role):
    """대소문자, 구두점과 한글 접미어가 있어도 명시적 영문 권한을 인식한다."""
    assert raw_intent(f"payment-core에 `{token.upper()}` 권한 주세요").requested_role == role
    assert raw_intent(f"payment-core {token}권한 주세요").requested_role == role


@pytest.mark.parametrize(
    "word",
    [
        "readme",
        "already",
        "thread",
        "spreadsheet",
        "rewrite",
        "administer",
        "ownership",
        "read2",
        "2read",
        "read_only",
        "_write",
        "pushback",
        "copilots",
    ],
)
def test_ascii_word_characters_block_token_boundaries(word):
    """영문자·숫자·밑줄에 이어진 토큰을 별도 권한이나 작업으로 인식하지 않는다."""
    assert raw_intent(f"{word} 작업 문의").requested_role == ""


@pytest.mark.parametrize(
    "contents,model_role,expected_role",
    [
        ("payment-core의 thread 작업이 안 돼요", "Write", "Write"),
        ("payment-core README 수정을 push하려는데 안 돼요", "Write", "Write"),
        ("payment-core Admin권한 주세요", "Read", "Admin"),
    ],
)
async def test_llm_role_preserves_valid_explicit_requests_only(
    monkeypatch,
    contents,
    model_role,
    expected_role,
):
    """부분 문자열로 모델 해석을 덮어쓰지 않고 명시적 Admin 요청은 보존한다."""

    class FakeModel:
        def with_structured_output(self, schema):
            """네트워크 연결 없이 구조화된 응답을 제공한다."""
            return self

        async def ainvoke(self, messages):
            """모델이 해석한 권한을 테스트 입력대로 반환한다."""
            return Intent(resource_hint="payment-core", requested_role=model_role)

    monkeypatch.setattr(planner, "settings", replace(planner.settings, mode="llm"))
    monkeypatch.setattr(planner, "model", FakeModel)
    assert (await planner.interpret(contents, "GITHUB")).requested_role == expected_role


def test_model_client_is_reused_without_caching_responses(monkeypatch):
    """같은 모델 연결 객체를 재사용하고 생성자를 한 번만 호출하는지 확인한다."""
    created = []

    def fake_client(**kwargs):
        """실제 모델 연결 대신 생성 횟수를 기록할 객체를 반환한다."""
        client = object()
        created.append(client)
        return client

    monkeypatch.setenv("LLM_API_KEY", "test-placeholder")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setattr("langchain_openai.ChatOpenAI", fake_client)
    model.cache_clear()
    try:
        first = model()
        assert model() is first
        assert len(created) == 1
    finally:
        model.cache_clear()


def test_model_without_credentials_does_not_construct_client(monkeypatch):
    """필수 설정이 없으면 모델 클라이언트를 생성하기 전에 실패한다."""

    def unexpected_client(**kwargs):
        """필수 설정이 없는 상태에서 생성자가 호출되면 테스트를 실패시킨다."""
        pytest.fail("설정이 없으면 모델 연결 객체를 만들면 안 됩니다.")

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr("langchain_openai.ChatOpenAI", unexpected_client)
    model.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="LLM mode requires"):
            model()
    finally:
        model.cache_clear()
