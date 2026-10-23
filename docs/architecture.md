# UnlockOps 업무 실행 구조

서버·에이전트·Worker·MCP는 현재 승인과 회수 업무를 한 가지 계약으로 처리합니다. 프론트 소스와 공개 API 응답은 유지했습니다.
기존 단일 승인 그래프·구 권한 writer·구 큐 소비·구 MCP 도구는 제거했습니다.

| 영역 | 진입점과 책임 |
|---|---|
| 승인 분석 | `agent/unlockops/access/graph.py`: 문맥 → 의도 → 정책 검색/정확 조회 → 서버 판정 → 안내 또는 승인 보고서 |
| 승인 실행 | `agent/unlockops/access/execution.py`: 최종 승인·계획·키 재확인 → 실행 → 독립 검증 |
| 회수 점검 | `agent/unlockops/reclaim/graph.py`: 고정 스냅샷·전체 페이지·알림 이력 검증 → 후보 설명 |
| Worker | `worker/unlockops_worker/runtime.py`: 작업 라우팅·체크포인트·완료 이벤트 저장과 재사용 |
| 서버 | `access`, `reclaim`, `common/workflow`, `messaging/workflow`: 업무 상태·정책·트랜잭션·이력 |
| MCP | 현재 업무 API와 회사별 정책 검색을 공유 스키마로 노출 |

승인 대기는 서버의 단계별 기록으로 관리합니다. 분석 그래프는 승인안을 반환하고 종료합니다.
사람의 모든 승인이 완료되면 서버가 별도 실행 작업을 발행합니다. 보류·수동 검토 재개는 새 event_id와 계획 버전으로 재분석합니다.

일반 권한·접근 문의는 현재 회사의 공식 요약·진단 힌트로 안내합니다. 필요한 권한을 이미 가진 오류 문의도 문서 기반 점검 안내로 연결합니다.
문서에 없는 절차는 만들지 않으며 근거 부족·안내 모델 장애는 MANUAL_REVIEW입니다.
직접 권한 신청에서 이미 권한을 보유한 경우에는 기존처럼 간단한 보유 안내로 완료합니다.

| 결과 | 의미 |
|---|---|
| DONE / GUIDANCE | 안내 제공 완료. 권한 변경·오류 해결을 주장하지 않음 |
| DONE / ACCESS_VERIFIED | 필수 승인·모의 부여·영수증·독립 제공자 재조회 성공 |
| MANUAL_REVIEW | 근거·요청 범위·모델 등 추가 검토 필요 |
| ON_HOLD | 예산 부족 또는 승인자의 보류. 재개 시 처음부터 최신 조건으로 승인 |
| 회수 DONE | 전체 조회·결과 저장·필수 인앱 알림 완료. 실제 권한 회수 완료가 아님 |

공통 업무 모델은 `common/workflow_contracts.py`, 도구 모델은 `common/tool_contracts.py`, registry·검증은 `common/contracts.py`입니다.
`MCPTools`는 연결·타임아웃·응답 검증, `WorkflowTools`는 작업별 허용 도구·범위·계획 고정·호출 한도·제한 재시도를 담당합니다.
LLM 설정은 `common/llm.py`, 승인·회수 설명 생성은 `common/reporting.py`를 공유합니다.

정책은 서버의 회사·revision·해시에 고정합니다. 안내는 공식 참고, 승인 보고서는 업무별 검토 근거를 선택하며 사실과 규정을 구분합니다.
가격·예산·TF 소속은 서버가 관측한 사실이며 정책 예시로 대체하지 않습니다.
`AccessCosting`은 가격표의 참고 단가와 이번 요청의 예산 반영액을 분리합니다. 회사·사용자·플랫폼·조직 범위·라이선스 코드가 일치하는 `saas_license_facts`와 정책에 연결된 `access_cost_rules`를 사용합니다. 기존 라이선스의 권한 추가는 0, 신규 구매가 확인된 좌석 요청은 추가 좌석 비용, 사용량 요청은 내부 예산 배정으로 처리합니다. 미확인은 수동 검토합니다. 실행 시 예산과 라이선스 사실을 잠근 뒤 최신 계획을 재검사하고 모의 좌석 확보와 관측 갱신을 같은 트랜잭션에 저장합니다.
권한 부여·예산 차감·영수증·작업 outbox는 서버 트랜잭션과 멱등 키로 통제합니다.
결과의 event_id는 중복 방지, job_event_id는 현재 분석/실행 세대 확인에 사용합니다.

프론트 호환을 위해 `/api/v2/problems`, `/api/reclaim`, schema_version=2와 기존 큐 이름을 유지합니다.
승인/회수 업무 구분과 정책·계획 revision은 계속 필요합니다. `data/phase2`와 `contracts/phase2`는 기존 fixture·생성 계약 경로이며 추가 실행기를 뜻하지 않습니다.
적용된 Flyway V1~V8과 과거 이력은 보존합니다. 구 승인·큐 작업은 새 계획에 자동 이관하지 않습니다.

상세 API는 [API 명세](api-spec.md), 메시지는 [공통 계약](../contracts/phase2/README.md), 전환 내역과 검증은 [구현 기록](../IMPLEMENTATION.md)을 참고하세요.
