# UnlockOps 협업 안내

이 문서는 실습 초기의 권장 작업 규칙입니다. 팀 합의가 바뀌면 해당 항목을 수정합니다. 별도 자동 검사가 명시되지 않은 규칙은 팀원이 직접 확인합니다.

## 1. Git 컨벤션

브랜치·커밋·이슈·PR·리뷰·병합 규칙은 [Git 컨벤션](docs/git-convention.md)에서 관리합니다. 현재 사용하는 브랜치와 커밋 형식을 기준으로 정리했습니다.

문서의 예시를 변경할 때는 Git 컨벤션을 기준으로 맞춥니다. 브랜치 보호와 리뷰 필수 설정은 GitHub에서 별도로 적용해야 합니다.

## 2. 이슈와 PR 템플릿

- 새 기능은 [Feature 이슈 템플릿](.github/ISSUE_TEMPLATE/feature.md)을 사용합니다.
- PR 본문은 [PR 템플릿](.github/pull_request_template.md)을 따릅니다.
- 자동 담당자 지정과 양식 설정은 [GitHub 협업 설정](.github/GITHUB_SETUP.md)을 확인합니다.

## 3. 코드와 설정 작성

- 공통 서식은 [.editorconfig](.editorconfig)를 따릅니다. 편집기에 따라 EditorConfig 확장을 설치합니다.
- 줄바꿈 규칙은 [.gitattributes](.gitattributes)에서 관리합니다. 텍스트는 LF, Windows 실행 파일은 CRLF를 사용합니다.
- Vue·웹 설정 파일은 공백 2칸, Java·Python은 공백 4칸을 사용합니다.
- 환경변수 추가·변경 시 [.env.example](.env.example)과 영향을 받는 서비스 README를 함께 갱신합니다.
- 팀 공통 주소·API·MCP·이벤트 형식이 바뀌면 [docs](docs/README.md)에 계약을 정리합니다.
- 패키지 관리 도구를 정한 뒤 해당 잠금 파일을 커밋합니다. 같은 서비스에 여러 도구의 잠금 파일을 새로 섞지 않습니다.

## 구현 기록 갱신

매 작업마다 루트 [IMPLEMENTATION.md](IMPLEMENTATION.md)의 현재 단계, 변경 내용, 설계 의도, 검증 결과, 다음 작업을 갱신합니다. 새 정리 파일로 분산하지 않고 같은 파일의 작업 이력에 누적합니다.

## 4. PR 전 확인

- 변경한 서비스의 README에 정의된 빌드·테스트·코드 검사를 수행합니다.
- 아직 초기화되지 않은 서비스나 실행할 검사가 없는 문서 변경은 확인한 내용과 실행하지 못한 이유를 PR에 적습니다.
- 서비스 단위 테스트는 해당 서비스 내부에, 서비스 간 통합·시나리오 검증은 루트 `tests/`에 둡니다.
- 비밀값, 로컬 환경 파일, 생성된 데이터가 포함되지 않았는지 변경 목록을 확인합니다.

기본 CI는 변경 파일의 공백·충돌 표시를 검사합니다. 로컬 실행과 main 보호 설정은 [GitHub CI 안내](docs/github-ci.md)를 따릅니다. 서비스별 빌드·테스트는 초기화 후 해당 README와 워크플로에 추가합니다.

## 5. 공통 규칙을 변경할 때

| 바꾸려는 내용 | 수정할 파일 또는 위치 |
| --- | --- |
| 들여쓰기·인코딩 | `.editorconfig` |
| 줄바꿈·바이너리 판별 | `.gitattributes` |
| 환경변수 이름·예시 | `.env.example` |
| Git 제외 규칙 | `.gitignore` |
| 브랜치·커밋·리뷰 방식 | [Git 컨벤션](docs/git-convention.md) |
| 설치·실행 안내 | 루트 및 서비스별 `README.md` |
| 이슈·PR 양식과 자동화 | `.github/` |

공통 설정 변경은 영향받는 팀원과 PR에서 합의하고, 관련 안내를 함께 갱신합니다.
