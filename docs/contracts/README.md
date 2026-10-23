# 공통 계약

현재 계약 원본은 `agent/unlockops/common/workflow_contracts.py`와 `tool_contracts.py`입니다.
서버·Worker·MCP는 같은 업무와 도구 계약을 사용하며 구 단일 승인 해석기를 실행하지 않습니다.

- [업무·메시지·완료 계약](../../contracts/phase2/README.md)
- [공개·내부 HTTP 스키마](../../contracts/phase2/http.json)
- [MCP 도구 계약](mcp.md)
- [API 명세](../api-spec.md)

프론트 호환을 위해 schema_version=2, `/api/v2/problems`, `frontend/src/contracts/phase2.ts`와 생성 결과 경로는 유지합니다.
버전은 계약과 승인 이력을 구분하며 별도 업무 실행기를 의미하지 않습니다. 과거 계약의 DB 이력은 다시 쓰지 않습니다.
