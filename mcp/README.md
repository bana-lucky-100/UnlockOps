# MCP

`unlockops_mcp.policy`와 `unlockops_mcp.business` 두 프로세스가 현재 업무 도구만 제공합니다.
공통 HTTP 전송·인증·오류 처리는 `backend_client.py`, 업무 API 어댑터는 `workflow_backend.py`입니다.

| 서버 | 도구 | 서버 경로 |
|---|---|---|
| Policy | `search_workflow_policy`, `read_workflow_policy` | 작업 문맥에서 고정한 회사 정책을 로컬 검색·정확 조회 |
| Business | `get_access_request_context` | GET `/internal/v2/problems/{id}/context` |
| Business | `assess_access_request` | POST `/internal/v2/problems/{id}/assessment` |
| Business | `execute_access_plan` | POST `/internal/v2/problems/{id}/execute` |
| Business | `verify_access_plan` | POST `/internal/v2/problems/{id}/verify` |
| Business | `get_reclaim_check_context` | POST `/internal/v2/reclaim/context` |
| Business | `list_revocation_candidates` | POST `/internal/v2/reclaim/candidates` |
| Business | `get_reclaim_notification_history` | POST `/internal/v2/reclaim/notification-history` |

도구 정의는 `business_tools.py`, `policy_tools.py`에 있습니다. 공유 registry는 `agent/unlockops/common/tool_contracts.py`이며 서버와 클라이언트가 같은 입출력 검증기를 씁니다.
MCP는 DB에 직접 접근하지 않습니다. 도구 호출의 employee/resource/role을 임의 실행하지 않고 현재 작업 ID·승인 계획 해시·실행 키로 서버에 요청합니다.
권한 실행 도구만 쓰기 힌트를 가지며 승인 분석·회수 도구 범위에서는 호출할 수 없습니다.

정책 검색은 회사·정책 revision·해시·플랫폼을 고정합니다. 안내에는 공식 요약과 진단 힌트를, 승인 검토에는 검증된 승인 조항을 사용합니다.
가격·TF 소속·예산은 서버 관측값으로 확인하고 문서 예시로 대체하지 않습니다. `review_facts`는 보고서 작성용 읽기 사실이며 승인 허가를 대신하지 않습니다.

```sh
.venv/bin/python -m unlockops_mcp.policy
.venv/bin/python -m unlockops_mcp.business
.venv/bin/python -m pytest mcp/tests -q
```

MCP_TOKEN은 Worker → MCP, INTERNAL_API_TOKEN은 MCP → Spring 인증에 사용합니다. 서버는 세션 없이 서비스 토큰으로 인증합니다.
구 `grant_permission`, `verify_permission`, 파일 기반 `search_policy` 등 구 전용 도구는 등록하지 않습니다.
