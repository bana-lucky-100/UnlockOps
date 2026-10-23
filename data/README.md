# 정책과 시연 데이터

현재 업무의 원문·회사별 정책·가격·승인 경로·회수 사실·평가 입력은 `phase2/`에 있습니다.
폴더명은 기존 데이터와 생성 hash·경로를 보존하며 별도 실행 버전을 뜻하지 않습니다.

- `phase2/policies/policy_corpus.md`: 사내 규정·공식 요약 원문 28건. 권한 검토와 접근 문제 안내의 근거.
- `phase2/policies/company-*-policy-v3.md`: 현재 시나리오 v4에 연결하는 회사별 정책 묶음.
- `phase2/seed.sql`, `policies/apply.sql`, `policies/apply-v4.sql`: baseline·정책 revision 2·3의 불변 적용 파일.
- `phase2/scenarios-v4.json`: 현재 입력·기대값. catalog/seed의 baseline 가격과 구분.
- 루트 `policy_corpus.md`, `company-a-access-matrix.md`: 과거 단일 승인 자료. 현재 MCP가 직접 검색하는 별도 경로는 제거.

Compose 시연 시작은 baseline과 누락된 정책 revision 2·3을 하나의 트랜잭션으로 준비합니다.
이미 적용한 정책·가격·승인 경로 revision을 덮어쓰지 않습니다. 원문을 바꾸려면 새 revision과 연결 규칙·평가를 함께 준비해야 합니다.
직원 현재 상태·TF 소속·권한·예산은 문서 예시로 추정하지 않고 서버에서 조회합니다.
사용법 안내도 현재 회사·플랫폼에 고정한 공식 요약·진단 힌트를 사용합니다.

자세한 준비·수동 적용은 [시연 데이터](phase2/README.md), [정책 revision](phase2/policies/README.md)을 참고하세요.
생성 checkpoint·index·runtime 파일은 Git 제외 경로에 둡니다.
