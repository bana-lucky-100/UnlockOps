# RAG

현재 업무는 서버가 고정한 회사 정책 revision을 `unlockops_rag/revisions.py`로 검색합니다.
`search.py`의 문자 n-gram TF-IDF·코사인 유사도 유틸과 `corpus.py`의 문서 파서를 재사용합니다.
기존 파일 기반 정책 도구의 별도 실행 경로는 제거했습니다.

| 자료·구현 | 역할 |
|---|---|
| `data/phase2/policies/policy_corpus.md` | 수신한 사내 규정·공식 제품 요약 28건의 원문 |
| `company-*-policy-v3.md` | 회사별 승인 경로·시연 범위를 더한 immutable 정책 묶음 |
| `revisions.py` | 서버 회사·정책·revision·해시·플랫폼에 고정한 검색·정확 조회 |
| `approval.py` | 승인 근거 선택, 사내 규정·공식 참고·회사 흐름·시연 가정 구분 |
| `agent/unlockops/access/answering.py` | 권한·접근 문제 안내의 인용·원문 발췌·내용 검증 |
| `agent/unlockops/access/review.py` | 서버 관측값에 근거한 승인 보고서 입력 |

승인에는 해당 플랫폼과 COMMON 조항을 사용합니다. 안내에는 같은 범위의 공식 요약·진단 힌트도 사용합니다.
직원 현재 소속·권한·예산·가격은 문서 예시로 추측하지 않고 서버 사실로 확인합니다.
근거 부족은 수동 검토, 보고서 모델 실패는 검증된 템플릿으로 처리합니다.
현재 검색은 로컬 TF-IDF이며 임베딩 API 설정이 필요하지 않습니다. DocumentIndex의 파일 검색·임베딩 구현은 파서·검색 유틸로 남지만 별도 업무 실행기를 구성하지 않습니다.
`EMBEDDING_BASE_URL/MODEL/API_KEY`는 이 유틸에만 적용하며 현재 revision 검색을 전환하지 않습니다. `DATA_DIR`도 Settings에 남은 필드이며 현재 업무 자료 경로를 바꾸지 않습니다. 적용 범위는 [환경변수 안내](../docs/environment.md)를 참고하세요.

Compose 시연 초기화는 baseline → 정책 revision 2 → revision 3을 준비합니다. 원문을 수정한 것만으로 기존 DB revision을 덮어쓰지 않습니다.
수동 적용과 생성은 [정책 자료 안내](../data/phase2/policies/README.md), 문서별 역할은 [승인 RAG 점검](../docs/rag-approval-review.md)을 참고하세요.
