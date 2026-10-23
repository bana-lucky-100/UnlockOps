"""Shared model configuration for interpretation, guidance and review reports."""
import os
from functools import lru_cache

@lru_cache(maxsize=1)
def model():
    """LLM 연결 객체를 프로세스에서 한 번 만들고 재사용한다. 응답을 캐시하는 것은 아니다."""
    from langchain_openai import ChatOpenAI

    if not os.getenv("LLM_API_KEY") or not os.getenv("LLM_MODEL"):
        raise RuntimeError("LLM mode requires LLM_API_KEY and LLM_MODEL")
    return ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        temperature=0,
        timeout=30,
        max_retries=1,
    )
