# 현재 구조 검증 기록

2026-10-23 통합 작업 기준입니다. 프론트 소스·생성 타입·적용된 Flyway V1~V8은 변경하지 않았습니다.

| 검사 | 결과 |
|---|---|
| Python Agent·MCP·선택 live 검사·평가 준비 | 194 passed, 1 skipped. live 스택 검사는 명시 활성화 전까지 건너뜀 |
| 업무·HTTP 계약 생성물 일치 | 통과. 공개 API·응답·계획 hash 기준 유지 |
| 정책 import·시나리오 v4 생성물 일치 | 통과. immutable 원문·SQL·revision 보존 |
| Java main/test 소스 독립 컴파일 | 통과. IDE 출력과 분리한 Java 21 javac 사용 |
| Java JUnit 실행 | 28건 통과. 계약·승인/회수·보고서·시연 인증·데이터 준비·리스너·HTTP 보안 |
| Maven 표준 test | Surefire 의존성 캐시 부족으로 실행 불가. JUnit 직접 실행과 구분 |
| 기존 프론트 npm test | 19건 통과. requesterHome 검사는 @vue/compiler-sfc 미설치로 시작 실패 |
| Docker 전체 스택 | Docker 소켓 접근 거부로 미실행 |
| 실제 SaaS·유료 LLM | 미실행 |

통합 이후 핵심 검사는 다음과 같습니다.

```sh
.venv/bin/python -m pytest agent/tests mcp/tests tests scripts/phase2/test_evaluation.py -q
.venv/bin/python scripts/export_phase2_contracts.py --check
.venv/bin/python scripts/export_phase2_http.py --check
.venv/bin/python scripts/import_phase2_policy.py --check
.venv/bin/python scripts/align_phase2_v4.py --check
cd backend
mvn test
mvn verify -Pregression -Dit.test=WorkflowFoundationIT,CompletionMigrationIT
```

Docker 접근이 가능한 환경에서는 사용자 DB와 분리된 평가를 실행합니다.

```sh
python3 scripts/evaluate_phase2.py --run --suite smoke
python3 scripts/evaluate_phase2.py --run --suite full
```

새 시연 환경에서 실제 화면의 승인 순서·반려/보류·재개·안내·회수 추가 확인·인앱 알림을 확인합니다.
선택 live HTTP 검사는 [tests 안내](../tests/README.md)를 따릅니다.
구 단일 승인 실행기 전용 테스트는 제거하고 현재 그래프의 안내·인용·범위 제한·재시도·내구 재전달·MCP HTTP 검사로 이전했습니다.
과거 DB migration과 immutable revision 보존 검사는 유지합니다. 과거 테스트 수와 현재 테스트 수를 동일 기능의 통과율로 비교하지 않습니다.

기존 CR-03(과거 후보 결과 표시), CR-04(상태/승인 단계 조회 시점), CR-05(최근 100건 이후 승인 대기 누락)는 별도 결함으로 남습니다.
이번 실행 구조 통합으로 수정됐다고 간주하지 않습니다.
