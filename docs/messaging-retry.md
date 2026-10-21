# 결과 메시지 오류 분류와 재시도

Backend는 `unlockops.results` 소비 시점에 예외를 분류합니다. DLQ에 도착한 뒤 `x-death`만으로 원인을 추측하지 않습니다.
`FAILED`라는 업무 결과는 유효한 메시지일 수 있으며, 결과가 FAILED라는 이유만으로 DLQ에 보내지 않습니다.

## 분류와 처리

| 분류 | 판단 근거 | 처리 |
| --- | --- | --- |
| TRANSIENT_DATABASE | Spring transient/recoverable DB 예외, JDBC transient/recoverable 예외, 허용된 연결·경합 SQLSTATE | 기존 listener 정책으로 제한 재시도 |
| PERMANENT_DATABASE | 무결성 예외, SQLSTATE class 22/23/28/3D/3F/42 | 즉시 DLQ |
| INVALID_MESSAGE | 메시지 변환 또는 명시적 InvalidAgentMessageException | 즉시 DLQ |
| UNKNOWN | 위 규칙에 없는 오류 | 자동 재시도하지 않고 DLQ·담당자 확인 |

허용 SQLSTATE는 `08000/08001/08003/08006/08007/40001/40P01/55P03/57014`입니다.
이는 연결·트랜잭션 경합·잠금·쿼리 취소/타임아웃의 제한된 허용 목록이며 모든 DB 오류를 뜻하지 않습니다.
DB 연결/트랜잭션 예외 안의 ConnectException·SocketTimeoutException도 허용합니다. DB 경계 밖의 네트워크 예외는 UNKNOWN입니다.
형식 거절과 DB 인증/무결성 오류를 우선하므로 인증 오류가 pool timeout 안에 있어도 무의미하게 반복하지 않습니다.
SQLSTATE는 [PostgreSQL 오류 코드](https://www.postgresql.org/docs/16/errcodes-appendix.html)를 기준으로 합니다.

기본은 최초 포함 총 3회이고, 첫 실패 후 1초·다음 실패 후 2초 대기입니다. 분류기는 listener의 시도 허용 여부만 바꾸고
`spring.rabbitmq.listener.simple.retry`의 횟수·backoff 설정, outbox 발행, HTTP/Worker/MCP 메시지 계약은 유지합니다.
DB 장애가 이 시간보다 길면 DLQ에 격리됩니다. 무기한 자동 복구나 장시간 지연 큐를 보장하지 않습니다.

계획 파싱·정책 위반·자원이 사라진 경우의 MANUAL_REVIEW는 유지합니다. 계획 검증 중 실제 DB 장애와 예상하지 못한 결함은
밖으로 전달하여 inbox·감사 이력·상태를 함께 롤백합니다. 매 재시도는 새 Service 트랜잭션이며 정상 반환 후 ACK합니다.
`DONE`에는 기존 verification_ok=true와 실행 영수증 조건이 여전히 필요합니다.

## DLQ와 종료 복구

처리 거절/재시도 소진은 DLQ 경로입니다. 서버·Worker가 ACK 전에 종료되는 경우는 원래 큐의 재전달 경로입니다.
DLQ 이동만으로 업무 상태가 FAILED가 되거나 승인·실행 키가 초기화되지는 않습니다.
DLQ 자동 재발행과 parking 큐는 없습니다. 원인을 수정한 뒤 같은 이벤트를 재처리할지, 올바른 새 업무 요청이 필요한지,
원본 감사/오류 기록을 보존하고 종료할지를 담당자가 판단합니다. 승인 계획을 임의로 수정해 실행하지 않습니다.

## 검증

기본 단위 테스트와 실제 DB·브로커 회귀는 다음 명령을 사용합니다.

```sh
cd backend
mvn test
mvn verify -Pregression -Dapi.version=1.44
```

`MessageRetryIT`의 fixture는 일회용 PostgreSQL·RabbitMQ에서만 실행합니다.
inbox INSERT trigger에 SQLSTATE를 주입하며, transaction rollback에 영향을 받지 않는 sequence로 실제 시도 횟수를 셉니다.
실제 네트워크 단절 실험이나 Python Agent/MCP 전체 실행을 대신하지 않습니다.

| 시나리오 | 기대 결과 |
| --- | --- |
| 첫 DB 쓰기만 40001 실패 | 시도 2회, 같은 이벤트 inbox/감사 1건, 유효한 완료 fixture는 DONE, DLQ 0 |
| 40001 지속 | 시도 3회, inbox/감사 0건, 기존 상태 유지, DLQ 1 |
| 23514 제약 위반 | 시도 1회, 전체 롤백, DLQ 1 |
| P0001 미분류 오류 | 시도 1회, 전체 롤백, DLQ 1 |
| 검증되지 않은 완료 | 시도 1회, 전체 롤백, EXECUTING 유지, DLQ 1 |
| 잘못된 envelope | DB 처리 0회, 원본 메시지 DLQ 보존 |

같은 완료 이벤트의 중복 전송과 후속 이벤트를 이용해 실제 소비 완료까지 기다린 뒤 inbox/감사가 증가하지 않는 것도 확인합니다.
계획 검증 중 DB/예상하지 못한 오류의 전파와 정상 정책 거절의 수동 검토는 단위 테스트로 별도 검증합니다.

## 실제 화면 자동 캡처

Docker, Node 22+, Google Chrome이 필요합니다. 캡처 의존성은 임시 디렉터리에만 설치하며 frontend 의존성을 바꾸지 않습니다.
브라우저 설치/캡처를 생략하면 기존 회귀 실행에는 영향이 없습니다. 저장소 루트에서 실행합니다.

```sh
npm install --prefix /private/tmp/unlockops-retry-browser --no-audit --no-fund playwright@1.64.1
cd backend
PLAYWRIGHT_MODULE=/private/tmp/unlockops-retry-browser/node_modules/playwright/index.mjs \
  mvn verify -Pregression -Dapi.version=1.44 -Dretry.capture=true -Dit.test=MessageRetryIT
```

`-Dretry.capture=true`는 Testcontainers의 임의 포트로 열린 실제 Management UI에 로그인해 Queues 화면을 촬영합니다.
컨테이너는 테스트 종료 때 제거됩니다. 실제 개발 Compose나 개발 DB를 사용하지 않습니다.
일회용 브로커 자격 증명은 캡처 프로세스의 stdin으로 전달하고 산출물 JSON에는 저장하지 않습니다.

`backend/target/retry-evidence/`에 아래 세 시나리오별로 `*-rabbitmq.png`, `*-evidence.png`, `*-evidence.json`, `*-evidence.html`을 저장합니다.
첫 이미지는 실제 RabbitMQ 화면이고, 두 번째 이미지는 같은 실행에서 조회한 DB 결과를 렌더링한 검증 보고서입니다.

1. `01-transient-recovered`: 2회 시도 후 DONE·이벤트 1회 반영·DLQ 0.
2. `02-permanent-rejected`: 1회 시도 후 EXECUTING 유지·이벤트 롤백·DLQ 1.
3. `03-transient-exhausted`: 3회 시도 후 RECEIVED 유지·이벤트 롤백·DLQ 1.

수신 결과와 실행 영수증은 테스트 fixture입니다. 실제 Agent가 권한을 변경했다는 증거로 사용하지 않습니다.
일시 오류 재시도는 소비자 내부에서 일어나므로 broker Redelivered 증가를 필수 증거로 삼지 않습니다.
UUID·SQL sequence 측정·DB 상태와 inbox/감사 건수를 함께 봅니다. 큐가 비었다는 것만으로 업무 성공이라고 판단하지 않습니다.
Management UI의 Get messages로 메시지를 꺼내지 않고 metrics와 화면만 관측합니다.

산출물은 기존 target ignore 규칙에 따라 커밋하지 않습니다. `mvn clean`을 실행하면 삭제되므로 발표에 사용할 캡처는 별도로 복사합니다.
