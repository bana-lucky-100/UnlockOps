"""규정 검색과 원문 조회를 읽기 전용 MCP 도구로 공개한다."""

from functools import lru_cache
import os

import uvicorn

from unlockops_rag.search import DocumentIndex
from unlockops.settings import settings
from .auth import TokenAuth
from .contracts import READ_ONLY, ContractMCP

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8001"))
mcp = ContractMCP("unlockops-policy", host=HOST, port=PORT, stateless_http=True, json_response=True)


@lru_cache(maxsize=1)
def index():
    """첫 요청에서 만든 문서 인덱스를 이후 조회에서도 재사용한다."""
    return DocumentIndex(settings.data_dir / "policy_corpus.md", "policy")


@mcp.tool(annotations=READ_ONLY)
def search_policy(query: str, platform: str, limit: int = 5) -> dict[str, object]:
    """공통 규정과 선택한 플랫폼의 규정을 검색합니다. 원문과 출처·버전 메타데이터를 반환합니다."""
    if platform not in {"GITHUB", "JIRA", "SLACK", "NOTION"}:
        raise ValueError("Unknown platform")
    return {"hits": index().search(query, platform, limit)}


@mcp.tool(annotations=READ_ONLY)
def read_policy(doc_id: str, article: str = "") -> dict[str, object]:
    """지정한 규정 문서·조항의 원문을 정확히 읽습니다. 문서 ID는 파일 경로가 아닙니다."""
    return {"chunks": index().read(doc_id, article)}


if __name__ == "__main__":
    uvicorn.run(TokenAuth(mcp.streamable_http_app()), host=HOST, port=PORT)
