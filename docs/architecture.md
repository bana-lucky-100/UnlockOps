# 아키텍처와 구현 위치

```mermaid
flowchart TD
  V[Vue 3 요청 입력] --> S[Spring Boot 인증·접수]
  S <--> DB[(PostgreSQL)]
  S --> O[Transactional outbox]
  O --> Q[RabbitMQ 분석/실행 큐]
  Q --> A[Python LangGraph]
  A <--> P[Policy MCP]
  A <--> B[Business MCP]
  B <-->|내부 API·서비스 토큰| S
  A --> R[RabbitMQ 결과 큐]
  R --> I[Spring inbox·상태 전이 검사]
  I --> DB
  I --> AV[담당자 Vue 3 승인 카드]
  AV --> S
```

Spring은 사용자·요청·승인과 모의 SaaS의 권한·팀·예산·영수증을 소유합니다. Business MCP는 내부 API를 호출하며
업무 DB에 직접 연결하지 않습니다. 승인된 계획·현재 자격·근거 검증과 원자적 변경은 Spring이 수행합니다.
에이전트 워커도 업무 테이블을 직접 수정하지 않습니다.
에이전트 상태는 별도 SQLite 체크포인트 볼륨에 저장합니다. 이 버전은 체크포인트 워커 한 개로 실행합니다.

```mermaid
flowchart TD
  START --> interpret --> scope
  scope -->|범위 확정| context --> gather --> judge --> prepare_response
  scope -->|범위 밖·수동 검토| END
  prepare_response --> compose_response
  compose_response -->|안내·거절·수동 검토| END
  compose_response -->|부여 가능| approval
  approval -->|interrupt 후 승인 기록으로 재개| execute
  execute -->|성공| verify
  execute -->|일시 오류·총 3회 미만| retry --> execute
  execute -->|최종 실패·조건 변경| finish
  verify -->|미반영·일시 오류·총 3회 미만| verify_retry --> verify
  verify -->|영구 오류·형식 오류| finish
  verify -->|반영·최종 미확인| finish --> END
```

State에는 원본 작업, 해석 결과, 직원 사실, 자원, TF 소속, 현재 권한, 예산, 두 문서의 근거,
불변 실행 계획, 실행·검증 시도 횟수와 진행 이벤트가 들어갑니다.
의도에는 사용법 문의·오류 해결·권한 신청을 구분하는 request_type이 있고,
판정 후 handling에는 ANSWER / APPROVAL / REJECT / MANUAL_REVIEW를 기록합니다.
judge는 비동기 노드 하나로 동작합니다. 사용법 문의는 권한 제안 없이 ANSWER로 보내고,
금지 역할·대상 불명확·필수 규정 누락은 먼저 판정합니다. 나머지는 assess_permission에서
현재 원문과 RAG 근거를 확인하고, LLM 모드에서는 권한 제안을 받은 뒤 rules.evaluate로
실제 자격·원문 상한·승인 조건을 검증합니다. 이미 필요한 권한이 있으면 재부여 대신 ANSWER로 연결합니다.
permission_proposal은 내부 권한 검토안이고 result.proposal은 사용자 안내 문구입니다.
judge 이벤트에는 handling과 함께 권한 검토안·근거 ID·원문 해시를 보존합니다.
prepare_response는 조회·LLM 호출 없이 사실·판정·문서·작성 기준을 묶고 별도 response_context에 저장합니다.
현재 권한·상한·직무·직급과 자원별 조건을 포함하고, 미확인은 null로 유지합니다.
예산은 충족 여부만 전달하고 직원 ID·승인자 ID·실행 키는 답변 입력에서 제외합니다.
선택 플랫폼 안내 최대 5개와 회사 권한 문서 3·4·7절의 관련 청크 각 1개를 출처·버전·해시와 함께 전달합니다.
입력 준비 노드는 상태·역할·승인 계획을 변경하지 않습니다.
compose_response는 일반 안내와 승인·거절·수동 검토의 설명을 생성·검증합니다.
승인·거절·수동 검토는 proposal만 교체하고 상태·사유 코드·승인 계획·계획 해시를 보존합니다.
모델 장애·근거 부족·검증 실패 시 해당 판정의 기존 안내를 유지하며 데모도 고정 안내를 사용합니다.
승인 전에는 실행 완료를 표현하지 않습니다. 승인 후 finish의 완료 안내는 LLM 없이 고정 문구로 전달합니다.

답변 경로는 준비된 입력으로 안내를 작성합니다. 데모에서는 문서 원문을 발췌하고,
LLM 모드에서는 생성 후 별도 근거 검토를 거칩니다. 코드가 인용 ID·원문 발췌의 일치도 확인합니다.
일반 안내의 자료 부족·내용 미지원·모델 장애는 MANUAL_REVIEW입니다. 성공은 DONE / result_type=GUIDANCE로 전달하며
proposal에 답변을 담습니다. 안내 제공 완료를 뜻하고 실제 오류 해결·권한 반영 완료를 뜻하지 않습니다.
권한 반영 완료는 DONE / result_type=ACCESS_VERIFIED이며 verification_ok=true가 필요합니다.
V5 마이그레이션으로 result_type을 저장하고 과거 안내 성공 행을 변환합니다. 안내의 plan·verification_ok는 null입니다.

LLM 모드의 `planner.investigate`는 두 MCP의 도구 설명·입력 스키마를 받아 읽기 도구를 선택합니다.
`ScopedTools`는 직원·플랫폼·자원 범위와 호출 횟수를 제한합니다. 필수 조회는 선택 조회보다 먼저 코드에서
수행합니다. 실제 읽기 호출은 context를 포함해 최대 30회, 모델 선택 조회 시도는 최대 10회이며 선택 조회
한도가 소진돼도 이미 수집한 필수 근거로 판정합니다. 모델이 사실 조회를 생략하거나 근거를 문장으로
만들어도 권한 변경을 승인하지 않습니다. MCP 경계의 스키마·오류는 [공유 계약](contracts/mcp.md)으로 검증합니다.

승인 API는 ApprovalDecisionService에서 결정 검증·기록을 수행하고, ApprovedExecutionService에서 저장된 승인을
다시 조회해 실행 전환 여부를 결정합니다. ApprovalCompletionPolicy는 현재 한 번의 사람 승인 완료를 판단하며,
Phase 2에서 단계별 승인 기록을 연결할 확장 지점입니다. 결정·이력·실행 전환·outbox는 같은 트랜잭션입니다.

승인 카드의 계획 SHA-256과 UI가 제출한 해시를 비교합니다. 승인 시 Spring이 조건과 승인자를 재검증하고,
Business MCP가 호출하는 Spring 실행 API도 실행 직전 DB 승인·계획 해시·TF·직무·부서·예산을 검사합니다. 모델이나 클라이언트는 실행 도구에
사용자·자원·역할을 임의 지정할 수 없습니다. 실행 도구 입력은 `problem_id`, `idempotency_key` 두 개뿐입니다.

권한 변경·예산 차감·실행 영수증은 같은 트랜잭션으로 커밋합니다. 사용자×자원 advisory lock과
예산 row lock으로 동시 중복 부여·좌석 중복 차감을 막습니다. RabbitMQ는 중복 전달될 수 있으므로
exactly-once 전송을 주장하지 않습니다. outbox/inbox와 실행 영수증으로 처리의 중복을 제어합니다.

기술 오류는 `FAILED`, 업무상 금지는 `REJECTED`, 예산 부족은 `REJECTED / BUDGET_INSUFFICIENT`, 자원·승인자 불명확은
`MANUAL_REVIEW`입니다. 정보가 부족해도 사용자에게 추가 질문을 보내지 않습니다.

요청자는 본인 요청만 조회하며, 공개 이력은 원본 에이전트 이벤트에서 정해진 안내 문장으로 변환합니다.
원본 evidence·도구 호출·실행 계획·해시는 요청자 응답에 포함하지 않습니다.
답변의 proposal에는 사용자에게 안내할 내용과 인용 문서·청크 ID를 포함합니다. 승인 및 변경 도구의 권한 검사는 유지합니다.

구현에서 참고한 공식 자료:

- [LangGraph 승인 대기·재개](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [공식 MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Spring AMQP 메시지 리스너](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html)
- [Vue 공식 시작 안내](https://vuejs.org/guide/quick-start.html)
