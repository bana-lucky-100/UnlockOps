# RAG

B팀 담당입니다. 문서 정제·청킹·검색 구현은 `unlockops_rag/search.py`에 있습니다.
MCP의 도구 정의는 `mcp/`에 두고 검색 로직만 이 폴더에서 관리합니다.

- `data/policy_corpus.md`: POL 조항과 플랫폼 요약. Policy MCP에서 검색·정확 조항 조회.
- `data/company-a-access-matrix.md`: 회사 상한표. Business MCP는 3·4·7절만 검색에 노출.
- 기본 검색은 문자 n-gram TF-IDF·코사인 유사도이며 별도 색인 서버가 필요하지 않습니다.
- `EMBEDDING_BASE_URL`과 `EMBEDDING_MODEL`을 함께 지정하면 외부 임베딩 API를 사용합니다.
- 검색 근거에 문서 ID·조항·버전·원문 SHA-256을 유지합니다.

루트 가상환경 설치 후 검증합니다.

```sh
.venv/bin/python -m pytest agent/tests/test_harness.py -q
```
