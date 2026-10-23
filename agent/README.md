# Agent

승인 분석·승인 후 실행·회수 점검을 업무별 그래프로 실행합니다. 기존 단일 승인 그래프와 Phase 2 실행기를 하나로 통합했습니다.

| 파일 | 책임 |
|---|---|
| `unlockops/access/graph.py` | 요청 해석 → 회사 정책 검색·검증 → 서버 판정 → 안내 또는 승인 보고서 |
| `unlockops/access/execution.py` | 서버 승인 계획 재조회 → 승인된 모의 권한 부여 → 독립 재조회 검증 |
| `unlockops/access/planner.py`, `intent.py`, `selection.py` | 요청 종류·명시 역할·플랫폼 해석, 허용 권한 항목 선택 |
| `unlockops/access/answering.py`, `response_context.py` | 문서 기반 안내, 인용·내용 검토, 모델에 전달할 사실 제한 |
| `unlockops/access/review.py`, `approval-review-guide.md` | 승인자별 검토 지침, 관측 예산·가격·TF 사실로 보고서 작성 |
| `unlockops/reclaim/graph.py` 및 역할별 모듈 | 정책 검토·후보 점검·보고서 작성 서브그래프, 부분 결과 보존 |
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

### 회수 Agent 역할

회수 Graph는 `context → policy_review → candidate_review → report_writer → finish`입니다.

`access`처럼 역할별로 파일을 나누되, 회수 폴더에서는 `phase2_` 접두사를 사용하지 않습니다.

| 파일                   | 담당 역할                                                            |
| ---------------------- | -------------------------------------------------------------------- |
| `reclaim/graph.py`     | 역할별 서브그래프 연결과 최종 이벤트 구성                            |
| `reclaim/state.py`     | 역할들이 공유하는 체크포인트 상태                                    |
| `reclaim/context.py`   | 점검 범위·실행 작업·스냅샷 확인                                      |
| `reclaim/policy.py`    | RAG 검색, POL-06 제5조 원문 조회와 인용 검증                         |
| `reclaim/scan.py`      | 모든 대상 페이지·사실 근거 검증, 기존 알림 이력 조회                 |
| `reclaim/reporting.py` | AI 설명 작성·불변 사실 검증, `candidates`·`needs_review` 보고서 구성 |

Worker의 `unlockops.reclaim.graph.build_graph` 진입점과 그래프 노드 이름은 유지합니다.
파일 분리로 점검을 다시 실행하거나 체크포인트 키를 변경하지 않습니다.

정책 검토는 고정된 문서의 **POL-06 제5조**를 정확한 조항 제목으로 읽고 문서 ID·묶음 revision·해시·조항과 원문 쌍을 확인합니다.
후보 점검은 기존 읽기 MCP의 모든 페이지·중복·스냅샷·근거를 검증합니다. 서버가 확정한 판정과 금액을 LLM이 다시 결정하지 않습니다.
보고서 작성은 새로 설명할 확정 후보만 모델에 보내며, 정보 부족·유지·제외·이미 알린 대상에는 모델을 호출하지 않습니다.
설명 오류는 기존 정형 문구로 대체하고, 작성 뒤에도 판정·금액·근거·할당 ID가 바뀌지 않았는지 코드로 검증합니다.

프론트와 합의한 **AI 보고서**와 현재 서버의 **큐 이벤트**를 분리했습니다. 프론트·백엔드·생성 DTO는 이번 수정에서 바꾸지 않습니다.

```python
from unlockops_worker.runtime import run_reclaim_report, read_reclaim_report

# ReclaimJob + 기존 AsyncSqliteSaver/InMemorySaver를 사용합니다.
report = await run_reclaim_report(job, saver, tools)
# 완료된 Agent 보고서만 읽기: 재조회·LLM·알림·체크포인트 쓰기 없음
report = await read_reclaim_report(job, saver)
```

AI 보고서에는 다음 필드가 있습니다.

```json
{
  "task_type": "RECLAIM_SCAN",
  "status": "EXECUTING",
  "reason_code": "SCAN_IN_PROGRESS",
  "scan_complete": true,
  "summary": { "needs_review_count": 1, "candidate_count": 0 },
  "needs_review": [
    {
      "assignment_id": "<UUID>",
      "user_name": null,
      "platform": "GITHUB",
      "missing": ["비용 근거"]
    }
  ],
  "candidates": []
}
```

- `needs_review_count`는 `needs_review` 배열 길이와 같습니다. `candidates`는 확인된 PENDING_REVIEW만 포함합니다. 기존 미검토 후보도 목록에서 자동 삭제하지 않습니다.
- 일부 조회 실패는 `FAILED / SCAN_FAILED`, `scan_complete=false`이며 검증된 부분 행만 보존합니다. 메시지 크기 한도가 있으면 한도 안의 앞부분을 남기고 건수를 다시 계산합니다. 이 값은 전체 조회 집계가 아닙니다.
- Worker는 기존 `ReclaimEvent/result/targets` 형식으로 전달합니다. 새 UI 필드를 strict 서버 이벤트에 섞지 않습니다. 서버 연결 담당자는 위 AI 보고서의 `candidates`/`needs_review`를 공개 응답에 연결해야 합니다. 현재 S-04 API가 자동으로 바뀐 것은 아닙니다.
- Agent는 DONE을 확정하지 않습니다. 결과 저장·필수 알림이 성공하면 서버가 SCAN_COMPLETED 또는 NO_NEW_CANDIDATES를 정하며, 추가 확인이 있으면 NO_NEW_CANDIDATES를 쓰지 않습니다.
- 현재 MCP에는 사용자 이름·원본 TF 종료일·실제 마지막 사용일이 없습니다. 이름은 null, 부족 정보는 확인 가능한 범위로만 반환합니다. `fact_evidence.observed_at`은 사용일로 바꾸지 않습니다.
- 이후 사실 조회가 보강되면 `display_facts={assignment_id: {"user_name": ..., "resource_name": ..., "last_used_at": ..., "missing": ["마지막 사용일", "TF 종료일"]}}`를 보고서 함수에 전달할 수 있습니다. 모델 설명에서 이름·날짜·누락 원인을 추출하지 않습니다. 이 메타데이터는 판정·금액·알림 여부를 바꾸지 않습니다.

이 변경은 실제 회수·외부 알림·인덱스/정책 교체·스케줄 활성화를 수행하지 않습니다.
