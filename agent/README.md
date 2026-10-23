# Agent

승인 분석·승인 후 실행·회수 점검을 업무별 그래프로 실행합니다. 기존 단일 승인 그래프와 Phase 2 실행기를 하나로 통합했습니다.

| 파일 | 책임 |
|---|---|
| `unlockops/access/graph.py` | 요청 해석 → 회사 정책 검색·검증 → 서버 판정 → 안내 또는 승인 보고서 |
| `unlockops/access/execution.py` | 서버 승인 계획 재조회 → 승인된 모의 권한 부여 → 독립 재조회 검증 |
| `unlockops/access/planner.py`, `intent.py`, `selection.py` | 요청 종류·명시 역할·플랫폼 해석, 허용 권한 항목 선택 |
| `unlockops/access/answering.py`, `response_context.py` | 문서 기반 안내, 인용·내용 검토, 모델에 전달할 사실 제한 |
| `unlockops/access/review.py`, `approval-review-guide.md` | 승인자별 검토 지침, 관측 예산·가격·TF 사실로 보고서 작성 |
| `unlockops/reclaim/graph.py` | 고정 스냅샷의 모든 페이지·알림 이력 확인, 후보 설명 |
| `unlockops/common/workflow_contracts.py` | 공통 업무·계획·이벤트·완료 계약과 canonical hash |
| `unlockops/common/tool_contracts.py`, `contracts.py` | 현재 도구의 단일 입력·출력 registry와 오류 형식 |
| `unlockops/common/tools.py`, `runtime.py` | MCP 연결, 작업별 도구·범위·실행 허가·호출 한도·재시도 |
| `unlockops/common/llm.py`, `reporting.py` | 공유 모델 설정과 확정 사실 기반 설명 생성·검토 |

사람의 승인 대기·반려·보류·재개는 Spring이 관리합니다. 분석 그래프에 승인 interrupt를 두지 않습니다.
최종 승인이 끝나면 서버가 EXECUTE 작업을 발행하며, 실행 그래프가 모든 승인과 계획 해시·실행 키를 다시 확인합니다.

일반 GUIDE 문의와 필요한 권한을 이미 보유한 오류 문의는 회사·플랫폼에 고정한 규정·공식 요약으로 안내합니다.
인용 ID·원문 발췌와 내용을 검증하며 문서에 없는 SSH·remote 설정 같은 절차를 만들지 않습니다.
안내 근거 부족·모델 장애는 수동 검토, 안내 성공은 DONE/GUIDANCE입니다. 실제 권한 변경 완료는 DONE/ACCESS_VERIFIED와 독립 검증 성공이 필요합니다.

승인 보고서는 사내 규정·공식 제품 참고·회사 승인 경로·시연 가정을 구분합니다. `review_facts`가 없으면 예산·TF 소속을 문서 예시로 채우지 않습니다.
회수는 신규·확정·미통지 후보만 모델로 설명하며 최종 저장·필수 알림·DONE은 서버가 확정합니다.

```sh
.venv/bin/python -m pytest agent/tests -q
.venv/bin/python scripts/export_phase2_contracts.py --check
```

실행은 [Worker](../worker/README.md), 자료와 지원 범위는 [승인 RAG 점검](../docs/rag-approval-review.md)을 참고하세요.
