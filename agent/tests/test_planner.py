"""LLM 연결 객체 재사용을 검사한다. 실제 모델 API는 호출하지 않는다."""

import pytest

from unlockops.planner import model


def test_model_client_is_reused_without_caching_responses(monkeypatch):
    created = []

    def fake_client(**kwargs):
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
    def unexpected_client(**kwargs):
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
