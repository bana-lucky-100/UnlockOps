# Backend

A2 담당입니다. Java 21, Spring Boot 3.5.7, Maven을 사용합니다.
인증·요청·지정 승인·상태·이력·내 담당 요청 집계과 RabbitMQ outbox/inbox를 관리합니다.
DB 스키마와 데모 데이터는 Flyway V1~V3에 있습니다. 기존 V1/V2를 수정하지 않습니다.

이 폴더에서 실행합니다. 로컬 DB·RabbitMQ와 환경변수가 필요합니다.

```sh
mvn test
mvn package -DskipTests
mvn spring-boot:run
```

구조 변경 전후 회귀 검증은 Docker를 실행한 뒤 아래 명령을 사용합니다.
Testcontainers가 별도의 PostgreSQL·RabbitMQ를 만들고 종료 시 제거합니다. 기존 실행 환경의 DB는 사용하지 않습니다.

```sh
mvn verify -Pregression
# 로컬 Docker에서 API 버전 오류가 발생하는 경우:
mvn verify -Pregression -Dapi.version=1.44
```

`src/test/java/com/unlockops/regression/BackendRegressionIT.java`는 원본 코드에서 작성·통과시킨
HTTP·DB·실제 큐 계약 테스트입니다. 애플리케이션 내부 클래스와 메서드에 의존하지 않으며,
리팩토링 뒤에도 동일한 테스트로 검증합니다. 기본 `mvn test`는 Docker 없이 단위 테스트만 실행합니다.
회귀 프로필은 Docker가 없으면 실패하므로 검증 누락을 성공으로 처리하지 않습니다.
Python worker 대신 결과 JSON을 발행하므로 실제 Agent/MCP 권한 부여의 전체 스택 테스트는 별도로 필요합니다.

루트 .env가 Maven에 자동 전달되지는 않습니다. VS Code의 Spring Boot 구성은 루트 .env를 읽습니다.
터미널에서 데모를 실행하면 `DEMO_ENABLED=true`, `DEMO_PASSWORD`와 DB·RabbitMQ 변수를 전달해야 합니다.
전체 컨테이너 실행은 루트 `docker compose up --build`를 사용합니다.

[API·메시지 계약](../docs/contracts/README.md), [디버깅 안내](../docs/debugging.md).
