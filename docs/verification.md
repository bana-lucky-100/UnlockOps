# 검증 기록과 재현 절차

## 이식 후 확인

- `.venv/bin/python -m pytest -q`: 30 passed, 1 skipped. 전체 스택 옵트인 테스트 1개만 건너뛰었습니다.
- `frontend/npm run build`: Vue TypeScript 검사와 Vite 빌드 통과.
- 기본 Compose와 로컬 디버그 override의 `docker compose config -q` 통과.
- Python wheel 빌드 및 agent·rag·mcp·worker 네 패키지 포함 검사 통과.
- Spring 테스트는 Maven 저장소 접근 제한으로 의존성을 받지 못하여 미완료입니다.
- Docker 엔진이 실행 중이지 않아 이미지 빌드·전체 스택·Flyway 실제 적용은 미검증입니다.
- 유료 LLM·외부 임베딩은 호출하지 않았습니다.

Python 그래프 테스트의 가짜 MCP는 실제 큐·DB 통합 검증을 대신하지 않습니다.
MCP HTTP 검사는 실제 ASGI 앱의 인증·초기화·도구 검색을 확인하며 DB 변경은 하지 않습니다.

## 내 승인 현황 집계 수정 검증

- Frontend TypeScript 검사·Vite 빌드 통과.
- ProblemService의 집계 SQL을 PostgreSQL 엔진(PGlite)에서 실행하여 동일 부서 승인자별 분리, 타 부서 요청자 포함, 0건, KST 주간 양끝 경계, 100건 초과, 승인·실패 중복 집계와 부서 프로필 유지를 확인했습니다.
- 같은 검증 데이터에서 기존 부서 기준 SQL의 숫자 불일치를 재현했습니다. 이 검사는 Spring HTTP·실제 운영 DB 통합 검증을 대신하지 않습니다.
- 전체 스택 테스트에 박리더 담당 요청이 윤부장 집계에 포함되지 않는 회귀 검사를 추가했습니다. 테스트 수집은 통과했으며 전체 스택 실행은 미완료입니다.
- Maven 저장소 접근 제한으로 이번 수정의 Spring 테스트 실행은 미완료입니다.

## 로컬 검증 명령

루트에서 실행합니다.

```sh
uv --cache-dir .cache/uv sync --extra test
.venv/bin/python -m pytest -q
docker compose config -q
docker compose -f compose.yaml -f infra/compose.debug.yaml config -q
```

backend에서 `mvn test`, frontend에서 `npm ci`와 `npm run build`를 실행합니다.

## 실제 서비스 통합 확인

1. README의 Docker Compose 명령으로 새 시연 환경을 실행합니다.
2. `kim_dev`로 S1-a 등록. `/api/problems`는 403, `?mine=true`와 본인 상세는 200이어야 합니다.
   요청자 상세·목록에 근거·계획·해시·내부 실행 키가 없어야 하고 events.payload에는 message만 있어야 합니다.
   타인 요청 조회·승인과 `/api/approvals/summary`는 403이어야 합니다.
3. `park_lead`로 로그인. 근거·대상·Write 계획을 확인하고 승인합니다.
4. DONE과 실제 GitHub 팀 멤버십 반영을 확인합니다. `song_ops`는 볼 수 있지만 대신 승인할 수 없어야 합니다.
5. S1-b~d를 각각 등록·승인합니다. 네 건이 독립된 승인 카드로 처리되어야 합니다.
6. S2/S2-b는 직무·직급과 별개로 TF 비구성원 거절이어야 합니다.
7. S3/S8은 질문 화면 없이 MANUAL_REVIEW이어야 합니다.
8. E-005 S4 REJECTED / BUDGET_INSUFFICIENT, E-004 S9 REJECTED, E-001 S6/S7/S10 REJECTED를 확인합니다.
9. S5는 **아직 PAY 권한을 받지 않은 새 시연 데이터**에서 Jira 실패 옵션을 켜고 승인합니다.
   성공한 S1-b를 먼저 실행한 데이터에서는 이미 권한이 있으므로 S5 실패 경로가 발생하지 않습니다.
10. 실행 이력의 execute 시도 1·2·3, 최종 FAILED와 미부여 상태를 확인합니다.
11. 승인 대기에서 agent 컨테이너를 재시작한 뒤 승인하여 동일 체크포인트에서 이어지는지 확인합니다.
12. 브로커 메시지 재전달 상황에서도 같은 실행 키로 권한·예산이 중복 반영되지 않는지 확인합니다.
13. 별도 LLM 모드에서 모델 도구 선택과 실제 MCP 호출 기록을 확보합니다. 데모 모드는 이 증거를 대신하지 못합니다.
14. V3 적용 후 상태 CHECK가 8개이며 기존 ON_HOLD와 INSUFFICIENT_BUDGET 행이 변환됐는지 확인합니다.
    구 결과 메시지·체크포인트 재전달도 새 상태/코드로 처리되어야 합니다. 원본 감사 이력은 유지합니다.
15. 내 승인 현황은 KST 접수 주 시작 직전/직후, 0건, 100건 초과 데이터를 확인합니다. 같은 부서의 TF 리더·부서장이 서로의 요청을 집계하지 않아야 합니다.
    요청자가 다른 부서여도 본인에게 배정되면 포함합니다. 승인 후 실패는 approved와 failed, AI 자동 거절은 rejected에 포함합니다.
    부서명·구성원 수는 승인자 프로필 기준을 유지합니다. song_ops의 전체 목록과 본인 요약은 별도 범위임을 화면에 표시합니다.

새 시연 환경이 이미 실행 중일 때, 위의 인증·지정 승인자·중복 승인·Jira 실패 큐 경로를 자동 확인하는
옵트인 테스트는 다음 명령입니다. 이 테스트는 컨테이너나 DB를 생성하지 않고 실행 중인 환경에 시연 요청을 등록합니다.

```sh
RUN_LIVE_STACK=1 .venv/bin/python -m pytest tests/test_live_stack.py -v
```

동작 로그에는 직원·요청 ID, 도구명, 상태·오류 코드만 남기고 비밀번호·토큰·모델 서비스 원문 오류를 기록하지 않습니다.

## 남은 검증

- Maven 의존성 다운로드가 가능한 환경에서 backend 테스트·패키징.
- Docker 이미지 빌드, V3 마이그레이션과 실제 승인→큐→MCP→권한 부여 흐름.
- 요청자 정보 제한, 내 담당 요청의 KST 집계 SQL, 브라우저 화면 시연.
- SQLite 체크포인트는 단일 worker 전용입니다. worker 확장은 별도 설계가 필요합니다.
