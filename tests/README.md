# 통합 테스트

`test_live_stack.py`는 실행 중인 전체 데모 스택에 HTTP 요청을 보내 승인·큐·실패 경로를 검증합니다.
기본 테스트에서는 건너뜁니다. 컨테이너를 직접 시작하거나 DB를 초기화하지는 않지만 테스트 요청을 등록합니다.

새 데모 환경에서, PAY 권한을 아직 받지 않은 신청자로 검증합니다. 루트에서 실행합니다.

```sh
RUN_LIVE_STACK=1 .venv/bin/python -m pytest tests/test_live_stack.py -v
```

기본 그래프 테스트는 `agent/tests`, MCP HTTP 테스트는 `mcp/tests`, Java 테스트는 `backend/src/test`에 있습니다.
전체 검증 결과는 [verification.md](../docs/verification.md)를 참고하세요.

RabbitMQ 결과 소비의 일시·영구 오류 분류는 Backend의 `MessageRetryIT`가 일회용 DB·브로커에서 검증합니다.
`capture-message-retry.mjs`는 이 테스트의 선택 실행용 실제 대시보드/DB 결과 자동 캡처 도구입니다.
실행법과 Python 전체 스택 검증과의 차이는 [재시도 검증 안내](../docs/messaging-retry.md)를 참고하세요.
