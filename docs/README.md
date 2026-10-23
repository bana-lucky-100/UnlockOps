# Docs

- [간략 API 명세서](api-spec.md): Request·Response, Spring·Agent·MCP 역할 구분
- [아키텍처](architecture.md): 요청·승인·실행·상태 재개 흐름
- [API·MCP·이벤트 계약](contracts/README.md): 공통 상태·HTTP·큐 메시지
- [로컬 디버깅](debugging.md): 설치·시작 순서·F5 구성
- [검증](verification.md): 수행 결과와 전체 스택 시연 절차
- [메시지 재시도](messaging-retry.md): 일시·영구 오류 분류, DLQ와 자동 캡처
- [DB 스키마](schema.md), [정책 해석](policy-decisions.md), [평가 항목 대응](rubric.md)
- [이식 전 원본 README](imported-project-v2.md): 원본의 과거 실행 상태·경로 기록
- [Git 컨벤션](git-convention.md), [GitHub CI](github-ci.md), [협업 안내](../CONTRIBUTING.md)

API·MCP·이벤트를 변경하면 공통 계약과 영향을 받는 서비스 README를 함께 갱신합니다.

- [과거 준비 설계: 상태 계약 통일과 승인 책임 분리](phase2-foundation-refactor.md)

- [현재 공통 계약](../contracts/phase2/README.md)
- [시연·평가 데이터](../data/phase2/README.md)
- [승인 RAG 문서 점검과 보고서 연결](rag-approval-review.md)
- [누적 구현 기록과 설계 의도](../IMPLEMENTATION.md)

- [통합 전 정리 대상 점검 기록](phase2-consolidation-audit.md)
