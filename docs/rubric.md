# 평가표 대응과 확인할 증거

아래는 구현 위치 매핑입니다. 검증 범위와 미완료 항목은 verification.md에 기록합니다.
수업에서 정한 Harness 필수 목록이 별도로 있다면 이 목록과 대조해야 합니다.

| 평가 항목 | 구현 위치 | 시연·검증 증거 |
|---|---|---|
| Biz 아이템 10 | README, 담당자 승인 UI | 사내 SaaS 접근 지원 B2B: 개별 요청의 근거·승인·실행 기록 연결 |
| 아키텍처 10 | architecture.md, compose.yaml, docs/contracts | 화면·API·비동기 워커·MCP·저장소의 책임 구분 |
| Agent 설계 15 | graph.py, models.py | 실제 StateGraph 노드, 조건 분기, 재시도 루프, 승인 interrupt |
| Agent 구현 15 | planner.py, tools.py, worker/unlockops_worker/__main__.py | **LLM 모드** 도구 선택, 두 MCP 호출, 소스 근거, 진행 이벤트, 프로세스 재시작 후 체크포인트 재개 |
| MCP 20 | mcp/unlockops_mcp/policy.py, mcp/unlockops_mcp/business.py | 실제 MCP list_tools/call_tool, 설명·입력 스키마, 조회·변경 분리, 오류 출력 |
| Harness 20 | ScopedTools, rules.py, repository.py, tests | 도구 범위·횟수·시간 제한, 구조화 출력, 승인 게이트, 계획 결합, 멱등·진행 기록, 실패 주입 |
| 인증 10 | SecurityConfig, AuthController, GrantRules | 세션·BCrypt·CSRF, 요청자 ID 서버 확정, 결과 접근 제어, 지정 승인자·본인 승인 차단 |
| 큐 가산점 10 | OutboxPublisher, AgentResults, worker/unlockops_worker/__main__.py | 지속 큐, confirm/ack, 중복 전달 처리, 장애 후 재전달, Jira 총 3회 실행 시도 |

ISO/IEC 25010을 고려한 품질 목표는 다음처럼 실제 동작에 연결합니다. 표준 준수 인증이나 전체 항목 충족을 주장하지 않습니다.

- 기능 적합성: S1-a~d, S2/S4/S6~S10 판정과 실제 권한 재조회.
- 신뢰성: 체크포인트, DB outbox/inbox, 제한 재시도, 멱등 영수증.
- 보안성: 인증·CSRF·최소 권한·지정 승인자·금지 역할·직원 범위 제한.
- 성능: 도구·모델 단계 한도, 페이지 최대 100건, 브로커 prefetch와 단일 실행.
- 유지보수성: 화면/API/Graph/MCP/규정 로직 분리, 명시적 메시지 계약.
- 사용성: 상태 한글 표시, 담당자 근거 카드, 입력 label, 키보드 폼, 모바일 레이아웃.

기본 데모 모드는 경로 재현용입니다. 모델이 실제로 도구를 선택하는 평가에는 LLM 모드 실행 기록이 필요합니다.
