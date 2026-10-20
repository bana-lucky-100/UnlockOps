# Infra

C2 담당입니다. 전체 서비스 기준은 루트 `compose.yaml`입니다.
`python.Dockerfile`은 agent·rag·mcp·worker를 공통 Python 환경에 설치합니다.
Docker 의존성은 uv.lock에서 내보낸 requirements.txt로 고정합니다. 의존성 변경 시 루트에서 갱신합니다.

```sh
uv --cache-dir .cache/uv lock
uv --cache-dir .cache/uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file infra/requirements.txt
```

`compose.debug.yaml`은 로컬 디버깅을 위해 DB·RabbitMQ·API·MCP 포트를 localhost에만 공개합니다.

루트에서 실행합니다.

```sh
docker compose up --build
# 또는 로컬 Python/Java 디버깅용 DB·브로커만 실행
docker compose -f compose.yaml -f infra/compose.debug.yaml up -d postgres rabbitmq
```

데이터·체크포인트 볼륨은 stop 시 유지됩니다. 실행 중인 다른 컨테이너와 포트 충돌을 확인하세요.
전체 시작 순서는 [디버깅 안내](../docs/debugging.md)를 참고하세요.
