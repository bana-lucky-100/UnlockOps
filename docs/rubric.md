# 평가 항목별 현재 구현 위치

| 평가 영역 | 현재 구현과 확인 위치 |
|---|---|
| 요청·업무 설계 | `access/graph.py`, `access/execution.py`, `reclaim/graph.py`의 StateGraph·분기 |
| RAG 근거 | 회사별 immutable revision, `rag/unlockops_rag/revisions.py`, `approval.py` |
| 문서 기반 안내 | `access/answering.py`, `response_context.py`; 인용 ID·원문·내용 검토와 근거 부족 처리 |
| 승인 보고서 | `access/review.py`, 검토 지침, 서버 review_facts, `common/reporting.py` |
| MCP | 두 서버의 현재 9개 도구, `common/tool_contracts.py`, `mcp/contracts.py` |
| 실행 통제 | `common/runtime.py`의 도구·작업·계획 범위, 한도·재시도; Worker checkpoint 결과 재사용 |
| 사람 승인 | 서버 AccessWorkflowService의 순차 승인·본인 승인 금지·보류/재개·계획 해시/버전 |
| 실행·검증 | AccessExecutionService의 예산·할당·영수증 트랜잭션과 독립 제공자 재조회 |
| 회수 | ReclaimSnapshot/Policy/Result/WorkflowService의 전체 조회·UNKNOWN·후보/알림 중복 방지 |
| 메시지 신뢰성 | WorkflowJobs/Results, outbox/inbox, 발행 확인, 현재 job_event_id와 중복 event_id 검사 |
| 인증·조직 범위 | 세션·CSRF·서비스 토큰, WorkflowAccessControl의 회사·부서·플랫폼 담당 범위 |
| 검증 | 현재 Python·MCP HTTP·Java 검사, 시나리오 v4 격리 smoke/full 실행기 |

프론트는 기존 코드·공개 응답을 유지합니다. 현재 구현 검증과 DB·RabbitMQ 전체 통합 실행 여부는 [검증 기록](verification.md)을 따릅니다.
구 버전 전용 테스트 수를 현재 기능의 검증 완료 근거로 사용하지 않습니다.
