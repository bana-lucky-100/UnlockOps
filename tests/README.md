# 통합 테스트

현재 서버·승인/회수 그래프·MCP만 검증합니다. 구 단일 승인 실행기는 제거했습니다.

```sh
.venv/bin/python -m pytest agent/tests mcp/tests scripts/phase2/test_evaluation.py -q
python3 scripts/evaluate_phase2.py --run --suite smoke
python3 scripts/evaluate_phase2.py --run --suite full
```

평가 실행기는 사용자 DB와 분리된 Docker 프로젝트에서 migration·데이터 준비·전체 흐름을 실행합니다.
`tests/test_live_stack.py`는 별도로 준비한 새 시연 환경에 실제 요청·승인을 등록하는 선택 검사입니다.

```sh
RUN_LIVE_STACK=1 .venv/bin/python -m pytest tests/test_live_stack.py -v
```

A사 신청자 → 부서장 → 권한 담당자의 순차 승인과 독립 검증, 본인 승인/순서 우회 차단을 검사합니다.
이미 Copilot 좌석을 지급한 환경 대신 새 시연 환경에서 실행합니다. 기본 테스트에서는 건너뜁니다.
