# MCP

C1 담당입니다. SDK `mcp`와 이름이 충돌하지 않도록 구현 패키지는 `unlockops_mcp`입니다.

각 도구는 함수 바로 위의 `@mcp.tool(annotations=READ_ONLY)` 또는
`@mcp.tool(annotations=APPROVED_WRITE)`로 읽기·변경 성격을 표시합니다.
`READ_ONLY`와 `APPROVED_WRITE`는 `contracts.py`의 공통 힌트이며 실제 승인 검사는 Repository에서 수행합니다.
`@lru_cache(maxsize=1)`이 붙은 `index()`는 규정 인덱스를 처음 만들고 재사용합니다.
직원의 현재 권한·TF 자격·예산 조회를 이 인덱스 캐시로 대체하지 않습니다.

| 파일 | 역할 |
| --- | --- |
| `unlockops_mcp/policy.py` | Policy MCP: search_policy, read_policy |
| `unlockops_mcp/business.py` | 직원·자원·TF·현재 권한·예산·회사 규정 조회, 승인된 권한 부여·검증 |
| `unlockops_mcp/auth.py` | Bearer 토큰 인증 및 /health |
| `unlockops_mcp/contracts.py` | 공유 스키마 노출, 입출력 검증, 안전한 공통 오류 응답 |
| `unlockops_mcp/repository.py` | PostgreSQL 정확 조회와 모의 SaaS 변경·중복 방지·실행 직전 재검증 |

직원의 권한 상한은 기존 `company-a-access-matrix.md`의 3절 표를 직접 읽어 확인합니다.
`search_access_rules`는 기존 검색 결과·상한에 현재 두 규정 문서의 `source_hashes`를 추가로 반환합니다.
실행 시에는 현재 직원·TF·예산과 DB에 저장된 승인 계획·RAG 근거를 다시 확인합니다.
원문과 저장된 근거의 해시가 맞지 않으면 부여하지 않습니다. 승인자 ID·앱 역할·직급 검사,
계획 해시·실행 키·영수증·트랜잭션 검증은 유지합니다. LLM 제안 자체로 변경 도구를 실행할 수 없습니다.

루트 가상환경 설치 후 각각 별도 터미널에서 실행합니다.

```sh
.venv/bin/python -m unlockops_mcp.policy
.venv/bin/python -m unlockops_mcp.business
```

기본 로컬 주소는 `http://localhost:8001/mcp`, `http://localhost:8002/mcp`입니다.
서버별 `MCP_HOST`, `MCP_PORT`로 변경합니다. Docker에서는 두 서버 모두 각 컨테이너의 8000을 사용합니다.
MCP 연결과 /health에 `Authorization: Bearer <MCP_TOKEN>`이 필요합니다.

원본을 유지하여 Business MCP가 같은 DB의 모의 SaaS 테이블을 직접 사용합니다.
초기 계획의 backend API 경유 방식으로 변경하는 작업은 이번 이식에 포함하지 않았습니다.
인증·승인 상태의 최종 기록은 Spring이 관리하며 실행 시 MCP에서도 검증합니다.

도구별 계약은 `agent/unlockops/contracts.py`를 공유합니다. UUID·플랫폼·역할·검색 한도를 입력에서
검증하고, 응답 필수 필드·불리언·예산 형식을 확인합니다. 성공 응답의 기존 구조와 출처 메타데이터는
유지하며, 오류는 MCP `isError=true`와 `{ok:false,error:{code,message,retryable}}`로 반환합니다.
자세한 필드와 재시도 기준은 [MCP 계약](../docs/contracts/mcp.md)에 정리했습니다.

```sh
.venv/bin/python -m pytest mcp/tests -q
```
