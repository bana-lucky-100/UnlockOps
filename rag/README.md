# RAG

B팀 담당입니다. 문서 정제·청킹·검색 구현은 `unlockops_rag/search.py`에 있습니다.
MCP의 도구 정의는 `mcp/`에 두고 검색 로직만 이 폴더에서 관리합니다.

- `data/policy_corpus.md`: POL 조항과 플랫폼 요약. Policy MCP에서 검색·정확 조항 조회.
- `data/company-a-access-matrix.md`: 회사 상한표. Business MCP는 3·4·7절만 검색에 노출.
- 기본 검색은 문자 n-gram TF-IDF·코사인 유사도이며 별도 색인 서버가 필요하지 않습니다.
- `EMBEDDING_BASE_URL`과 `EMBEDDING_MODEL`을 함께 지정하면 외부 임베딩 API를 사용합니다.
- 검색 근거에 문서 ID·조항·버전·원문 SHA-256을 유지합니다.
- 에이전트 `answering.py`가 Policy MCP 검색 결과를 안내에 사용합니다. 데모는 원문 발췌,
  LLM 모드는 생성·내용 검토를 수행하고 인용 ID·원문 발췌를 코드로 검사합니다.
  안내 근거가 부족하면 수동 검토로 넘기며, 권한 판정·변경은 별도 정책·승인 검증을 유지합니다.
- `response_context.py`는 선택 플랫폼 안내 최대 5개와 Business MCP로 읽은 회사 권한 문서
  3·4·7절의 관련 청크를 각 1개씩 선택하고, 출처·버전·원문 해시를 보존합니다.
  prepare_response 노드는 이 문서들과 조회 사실·확정 판정을 묶어 LLM 생성·검토 양쪽에 전달합니다.

루트 가상환경 설치 후 검증합니다.

```sh
.venv/bin/python -m pytest agent/tests/test_harness.py -q
```

## Phase 2 정책 revision

`revisions.py`는 서버가 반환한 회사 정책의 content/source_hash를 검사한 뒤 조항으로 나눕니다.
회사·정책·revision·문서 ID·해시·본문별 불변 인덱스만 최대 32개 캐시합니다.
v2 검색은 로컬 TF-IDF이며 정확 원문 조회를 함께 사용합니다. v1 외부 임베딩 설정을 사용하지 않습니다.
작업 ID로 서버에서 정책을 선택하므로 다른 회사 corpus를 섞지 않으며 회수는 접수 시점의 정책을 고정합니다.
현재 근거는 data/phase2 합성 문서를 seed한 DB revision입니다. 실제 문서·가격 교체 및 규칙 갱신은 후속 단계입니다.

### 수신 규정 문서 revision 2

`data/phase2/policies/policy_corpus.md`에 제공받은 10개 SaaS 규정·공식 요약 28개를 보관합니다.
`corpus.py`가 메타데이터와 조항을 읽고 `scripts/import_phase2_policy.py`가 회사별 정책 묶음과 DB 적용 SQL을 생성합니다.
정책 묶음의 DB revision/해시와 원문 조항의 ID/버전을 함께 유지하며, 승인 요청은 해당 플랫폼과 공통 규정만 검색합니다.
원문을 추가하는 것만으로 실행 중 DB가 바뀌지는 않습니다. [적용 방법과 문서·구현 차이](../data/phase2/policies/README.md)에 따라 `apply.sql`을 적용해야 새 요청부터 revision 2를 사용합니다.
현재 금액은 mock 계약 값을 유지하며, 원문의 정가 예시로 자동 변경하지 않습니다.
