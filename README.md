# UnlockOps

AI가 서비스 접근 문제를 진단하고, 담당자 승인 후 필요한 권한 부여를 돕는 서비스입니다.

## 1. 현재 상태

팀별 폴더, 기본 협업 설정, 이슈·PR 템플릿을 준비한 초기 레포지토리입니다. 서비스 코드, 패키지 설정, DB·큐 실행 환경과 전체 실행 명령은 아직 추가하지 않았습니다.

서비스 프로젝트를 초기화할 때 해당 폴더의 README에 설치·실행·테스트 방법을 추가합니다.

## 2. 기술 구성

| 영역 | 사용 계획 | 확정이 필요한 항목 |
| --- | --- | --- |
| Frontend | Vue, Vite | Node 버전, 패키지 관리 도구 |
| Backend | Spring Boot, Java | JDK·Spring Boot 버전, Gradle 또는 Maven, 업무 DB |
| Agent | Python, LangChain, LangGraph | Python 버전, 패키지 관리 도구, LLM·임베딩 모델 |
| RAG | 문서 정제·색인·검색 | 문서 형식, 임베딩·벡터 저장소 |
| MCP | business MCP, rag MCP | 서버 구현 방식과 전송 방식 |
| 비동기 실행 | RabbitMQ, Python worker | 메시지 계약, 재시도·중복 처리 기준 |
| 개발 환경 | Docker Compose | 서비스 구성, 포트, 볼륨 |

버전과 실행 도구는 담당 팀 합의 후 서비스별 설정 파일과 README에 명시합니다. 현재 `.env.example`의 주소와 포트는 제안값이며 확정된 연동 계약이 아닙니다.

## 3. 폴더별 역할

| 폴더 | 역할 |
| --- | --- |
| [frontend](frontend/README.md) | Vue 사용자 화면 |
| [backend](backend/README.md) | 인증·업무 API·승인 상태·DB 관리 |
| [agent](agent/README.md) | 두 Agent, LangGraph, 프롬프트·상태 관리 |
| [rag](rag/README.md) | 문서 정제·색인·검색 구현 |
| [mcp](mcp/README.md) | 업무·검색 기능을 제공하는 MCP 서버 |
| [worker](worker/README.md) | RabbitMQ 작업 소비·실행·재시도 |
| [data](data/README.md) | 데모 정책·샘플 데이터·문서 출처 |
| [infra](infra/README.md) | RabbitMQ 등 공통 실행 환경 |
| [docs](docs/README.md) | API·MCP·이벤트 계약, 설계·실행 안내 |
| [tests](tests/README.md) | 서비스 간 통합·시나리오 검증 |
| [.github](.github/README.md) | 이슈·PR 템플릿과 GitHub 자동화 |

업무 규칙과 승인 상태의 최종 검증은 backend에서, 문서 검색 구현은 rag에서 관리합니다. MCP는 이 기능들을 도구로 제공하며, worker는 승인된 작업의 비동기 실행 흐름을 담당합니다.

## 4. 개발 준비

1. 레포지토리를 받은 뒤 [협업 안내](CONTRIBUTING.md)를 확인합니다.
2. 편집기에서 EditorConfig 지원을 활성화합니다. 필요하면 확장을 설치합니다.
3. 레포 루트에서 환경변수 예시를 복사합니다.

```sh
cp .env.example .env
```

Windows PowerShell에서는 다음 명령을 사용합니다.

```powershell
Copy-Item .env.example .env
```

4. 작업할 서비스에 필요한 값만 채웁니다. API 키와 비밀번호는 실제 사용 시 개인 `.env`에 입력합니다.
5. 서비스 초기화 후 해당 폴더의 README를 따라 의존성을 설치하고 실행합니다.

현재는 앱 실행이나 `docker compose up`을 위한 설정이 없습니다. 서비스 초기화와 `compose.yaml` 추가 후 이 절차에 실제 실행 명령을 연결합니다.

## 5. 환경변수 관리

[.env.example](.env.example)은 공통·Frontend·Backend·인증·DB·RabbitMQ·LLM·LangSmith·MCP·RAG 항목으로 나뉩니다. DB와 인증 방식 등 미정인 설정은 주석으로 예시를 남겼습니다.

| 대상 | 적용 방법 |
| --- | --- |
| Vue / Vite | 프로젝트 초기화 후 `frontend/.env.local`에 필요한 `VITE_*` 값만 복사합니다. 이 값은 브라우저에 공개됩니다. |
| Spring Boot | 실행 프로세스에 환경변수를 전달합니다. 표준 `SERVER_PORT`, `SPRING_*` 값 외에 프로젝트 공통 변수는 별도 설정 연결이 필요합니다. |
| Python 서비스 | 실행 환경변수 또는 경로를 지정한 dotenv 로딩을 구현합니다. |
| Docker Compose | 파일 추가 시 환경변수 치환과 컨테이너의 `environment` 또는 `env_file` 전달을 설정합니다. |

루트 `.env`는 각 서비스에 자동 적용되지 않습니다. 환경변수 로딩 방식은 서비스 초기화 시 README에 기록합니다.

- `localhost` 예시는 호스트에서 서비스를 실행하는 상황을 기준으로 합니다. 컨테이너 간 통신은 Compose 서비스 이름을 사용하도록 설정합니다.
- RAG 경로 예시는 레포 루트 기준입니다. 구현에서 루트 경로를 명시적으로 해석하거나 개인 `.env`에 절대경로를 입력합니다.
- Python worker의 `RABBITMQ_URL`과 Spring RabbitMQ 설정은 같은 브로커·계정·vhost를 가리키도록 맞춥니다.
- 원본 문서와 데모 데이터는 추적하고, 생성된 색인·임베딩·모델 캐시는 `.gitignore`에 지정된 폴더에 저장합니다.

## 6. 공통 설정 수정 위치

| 파일 | 관리하는 내용 |
| --- | --- |
| [.editorconfig](.editorconfig) | 인코딩, 들여쓰기, 파일 저장 형식 |
| [.gitattributes](.gitattributes) | Git 줄바꿈 정규화, 바이너리 비교 방식 |
| [.env.example](.env.example) | 필요한 환경변수 이름과 예시 |
| [.gitignore](.gitignore) | 비밀 설정·캐시·빌드·로컬 데이터 제외 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 브랜치·커밋·이슈·PR·리뷰 규칙 |

이슈 템플릿, PR 템플릿과 작성자 자동 담당자 지정은 기본 브랜치에 반영한 후 사용할 수 있습니다. 자동 담당자 지정에는 GitHub Actions 실행이 필요합니다.

## 7. 서비스 초기화 시 추가할 내용

- 각 서비스의 버전, 패키지 관리 도구와 설치·실행·테스트 명령
- 전체 실행을 위한 `compose.yaml`과 서비스 상태 확인 방법
- `docs/contracts/` 아래 API·MCP·이벤트 계약
- 실제 서비스가 준비된 뒤 빌드·테스트·코드 검사 자동화
