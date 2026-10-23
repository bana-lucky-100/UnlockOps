# MCP

C1 담당입니다. SDK `mcp`와 이름이 충돌하지 않도록 구현 패키지는 `unlockops_mcp`입니다.

각 도구는 함수 바로 위의 `@mcp.tool(annotations=READ_ONLY)` 또는
`@mcp.tool(annotations=APPROVED_WRITE)`로 읽기·변경 성격을 표시합니다.
`READ_ONLY`와 `APPROVED_WRITE`는 `contracts.py`의 공통 힌트이며 실제 승인 검사는 Spring 실행 API에서 수행합니다.
`@lru_cache(maxsize=1)`이 붙은 `index()`는 규정 인덱스를 처음 만들고 재사용합니다.
직원의 현재 권한·TF 자격·예산 조회를 이 인덱스 캐시로 대체하지 않습니다.

| 파일 | 역할 |
| --- | --- |
| `unlockops_mcp/policy.py` | Policy MCP: search_policy, read_policy |
| `unlockops_mcp/business.py` | 직원·자원·TF·현재 권한·예산·회사 규정 조회, 승인된 권한 부여·검증 |
| `unlockops_mcp/auth.py` | Bearer 토큰 인증 및 /health |
| `unlockops_mcp/contracts.py` | 공유 스키마 노출, 입출력 검증, 안전한 공통 오류 응답 |
| `unlockops_mcp/backend_client.py` | Spring 내부 API HTTP 호출, 기존 MCP 응답으로 투영, 인증·시간 제한·오류 변환 |

직원의 권한 상한은 Spring이 기존 `company-a-access-matrix.md`의 3절 표에서 읽어 반환합니다.
`search_access_rules`는 검색 결과·상한·현재 두 규정 문서의 `source_hashes`와 함께
Spring에서 한 번에 조회한 접근 조건을 `context`에 반환합니다.
Spring 실행 API는 현재 직원·TF·예산과 DB에 저장된 승인 계획·RAG 근거를 다시 확인합니다.
원문과 저장된 근거의 해시가 맞지 않으면 부여하지 않습니다. 승인자 ID·앱 역할·직급 검사,
계획 해시·실행 키·영수증·트랜잭션 검증은 유지합니다. LLM 제안 자체로 변경 도구를 실행할 수 없습니다.
원문 파일이 없거나 읽을 수 없으면 조회 도구는 `POLICY_SOURCE_UNAVAILABLE`을 반환합니다.
승인 후 실행에서도 규정 검사에 실패하면 권한 변경 전에 차단합니다. GitHub의 부여 후 검증은
Spring을 통해 실제 모의 팀 멤버십을 다시 조회합니다. 변경·검증 응답은 MCP에서 캐시하지 않습니다.

루트 가상환경 설치 후 각각 별도 터미널에서 실행합니다.

```sh
.venv/bin/python -m unlockops_mcp.policy
.venv/bin/python -m unlockops_mcp.business
```

기본 로컬 주소는 `http://localhost:8001/mcp`, `http://localhost:8002/mcp`입니다.
서버별 `MCP_HOST`, `MCP_PORT`로 변경합니다. Docker에서는 두 서버 모두 각 컨테이너의 8000을 사용합니다.
MCP 연결과 /health에 `Authorization: Bearer <MCP_TOKEN>`이 필요합니다.

Business MCP는 DB 드라이버·SQL·DB 자격 증명 없이 Spring 내부 API만 사용합니다.
로컬 `BACKEND_INTERNAL_URL=http://localhost:8080`, Compose에서는 `http://backend:8080`입니다.
`INTERNAL_API_TOKEN`은 Spring과 같은 값이며 기본값은 `replace-this-local-internal-api-token`입니다.
HTTP 요청 제한은 10초이며 자동 재시도·리다이렉트·DB fallback은 없습니다. 재시도는 Agent가 같은 실행 키로 수행합니다.

| MCP 도구 | Spring 내부 API |
| --- | --- |
| resolve_resource | POST /internal/resources/resolve |
| get_employee_profile | POST /internal/access-context (employeeId만 전달) |
| get_tf_membership / get_current_permissions / search_access_rules | POST /internal/access-context (employeeId·resourceId) |
| check_budget | POST /internal/access-context (employeeId·includeBudget=true) |
| grant_permission | POST /internal/problems/{id}/grant |
| verify_permission | POST /internal/access-verifications |
| read_access_rule / 규정 청크 검색 | 기존 로컬 문서 인덱스 |

기존 도구 입력·성공 응답과 Graph 노드 순서는 유지합니다. 각 조회 도구는 묶음 응답에서 필요한 필드를 반환합니다.
필수 분석은 `search_access_rules.context`의 직원·TF·현재 권한·좌석 예산을 한 번에 사용합니다.
자원별 묶음 API 호출은 기존 3회(좌석은 별도 예산 조회까지 4회)에서 1회로 줄었습니다.
같은 분석의 선택 조회에는 이미 받은 사실을 재사용하며, 다음 분석과 승인 후 실행·검증은 새로 조회합니다.
context 필수 응답 계약을 공유하므로 이 변경은 Agent와 Business MCP를 함께 배포합니다.
직원만 조회할 때는 자원·규정 판정을 수행하지 않고 예산도 명시적으로 요청한 경우에만 읽습니다.
자원 ID가 주어지면 Spring이 플랫폼을 확인하며 Agent의 ScopedTools 직원·자원·플랫폼 제한은 유지됩니다.
Spring과 MCP의 회사 권한표 해시가 다르면 상한을 섞어 사용하지 않고 규정 오류로 중단합니다.

도구별 계약은 `agent/unlockops/common/contracts.py`를 공유합니다. UUID·플랫폼·역할·검색 한도를 입력에서
검증하고, 응답 필수 필드·불리언·예산 형식을 확인합니다. 성공 응답의 기존 구조와 출처 메타데이터는
유지하며, 오류는 MCP `isError=true`와 `{ok:false,error:{code,message,retryable,reason?}}`로 반환합니다.
자세한 필드와 재시도 기준은 [MCP 계약](../docs/contracts/mcp.md)에 정리했습니다.

```sh
.venv/bin/python -m pytest mcp/tests -q
```

## Phase 2 도구

`phase2_business.py`와 `phase2_policy.py`를 기존 두 서버에 등록했습니다. 입출력 스키마는
`agent/unlockops/common/phase2_tools.py`를 공유하고 `phase2_backend.py`가 서버 응답을 검증·정규화합니다.

| 도구 | 내부 연결 |
|---|---|
| get_access_request_context | GET /internal/v2/problems/{id}/context |
| assess_access_request | POST /internal/v2/problems/{id}/assessment |
| execute_access_plan | POST /internal/v2/problems/{id}/execute |
| verify_access_plan | POST /internal/v2/problems/{id}/verify |
| get_reclaim_check_context | POST /internal/v2/reclaim/context |
| list_revocation_candidates | POST /internal/v2/reclaim/candidates |
| get_reclaim_notification_history | POST /internal/v2/reclaim/notification-history |
| search_workflow_policy / read_workflow_policy | 작업 context로 정책 revision을 확정한 뒤 로컬 검색·정확 조회 |

v2 변경 도구는 execute_access_plan 하나이며 서버가 최종 승인·현재 자격·계획 해시·실행 키를 검사합니다.
회수 도구는 모두 읽기 전용입니다. Policy MCP도 서버에서 회사별 정책을 확인하므로
BACKEND_INTERNAL_URL/INTERNAL_API_TOKEN이 필요합니다. v1 도구·문서 경로는 유지합니다.
