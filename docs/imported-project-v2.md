> 이식 전 mcp_project 2의 README 기록입니다. 아래 경로·검증 상태는 원본 시점이며 현재 실행 방법은 루트 README와 debugging.md를 따릅니다.

# UnlockOps

Vue 3 → Spring Boot → RabbitMQ → Python LangGraph → Policy MCP / Business MCP로
접근 권한을 진단하고, 지정 승인자 승인 후 **모의 SaaS**에 권한을 부여하는 캡스톤 프로젝트입니다.

**현재 작성 상태:** 기존 스택은 사용자가 Docker로 실행해 S1-a 승인·부여·검증 완료를 확인했습니다.
추가한 본인 조회·부서 요약·상태 8개 변경은 코드와 검증 코드만 작성했으며, 이번 변경의 테스트·빌드·DB 적용은 미실행입니다.

## 범위

- 한 요청은 한 플랫폼·한 자원만 처리합니다. S1은 제외하고 S1-a~d를 독립 접수합니다.
- 대화형 되묻기는 없습니다. 자원 누락·복수 자원은 `MANUAL_REVIEW`로 종료합니다.
- 요청자는 본인 요청의 처리 상태·안내·공개 이력을 조회합니다. 판단 근거와 승인 카드는 담당자만 조회합니다.
- 승인자 화면에 소속 부서의 이번 주 접수·승인·거절·실패 요약을 제공합니다.
- 예산 부족은 `REJECTED / BUDGET_INSUFFICIENT`로 종료합니다. 상태는 8개입니다.
- Admin / Owner / Full access는 거절합니다. 구두 승인은 시스템 승인을 대체하지 않습니다.
- TF 자원은 TF 리더, 일반·좌석 자원은 부서장이 승인합니다. 본인 승인과 임의 대체 승인은 불가합니다.
- GitHub는 자원별 전용 팀 멤버십으로 부여합니다. 예산 확인·중복 좌석 차단·부여 후 재조회를 구현합니다.
- Jira 실패 시연은 최초 포함 **총 3회(재시도 2회)** 시도합니다. 정보 추가 요청이나 다중 플랫폼 부분 성공은 구현하지 않습니다.

## 실행 준비 및 실행 명령

Docker와 Docker Compose가 필요합니다. 실행하면 새 컨테이너와 이 프로젝트 전용 볼륨을 만들고,
PostgreSQL에 Flyway 스키마와 가상 회사 A사 시드를 적용합니다. 기존 외부 서비스는 사용하지 않습니다.

```sh
cp .env.example .env
# .env의 데모 비밀번호와 MCP_TOKEN을 설정합니다.
docker compose up --build
```

- 화면: <http://localhost:8088>
- RabbitMQ 관리 화면: <http://localhost:15672> (`.env`의 RabbitMQ 계정)
- API·PostgreSQL·MCP는 Compose 내부 네트워크에서 통신합니다.
- 컨테이너 중단: `docker compose stop` (데이터 볼륨 유지)

데모 계정의 비밀번호는 `.env`의 `DEMO_PASSWORD`입니다. 계정 생성 시 한 번 BCrypt로 저장하며
재시작 때 기존 비밀번호 해시를 덮어쓰지 않습니다.

| 계정 | 용도 |
|---|---|
| `kim_dev` | S1-a~d, S3, S5~8, S10 요청 |
| `park_lead` | 결제 개편 TF 승인 |
| `lee_ops`, `oh_dev` | 비구성원 거절 |
| `jung_data` | Copilot 예산 부족 |
| `choi_copilot` | Copilot 중복 좌석 |
| `yoon_head` | 개발팀 일반 자원 승인 |
| `song_ops` | 운영 담당자 전체 이력 조회. 타인의 지정 승인 권한은 없음 |

## 모델과 RAG

기본 `AGENT_MODE=demo`는 API 키 없이 시나리오 경로를 재현하는 규칙 기반 해석기입니다.
**이 모드에서는 LLM이 도구를 선택했다는 평가 증거가 되지 않습니다.** 실제 모델 도구 선택을 시연하려면
`AGENT_MODE=llm`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`을 지정합니다.
LLM은 MCP의 읽기 도구만 선택할 수 있으며, 필수 사실·규정은 코드가 다시 조회하고 권한 변경은 별도 승인 게이트를 거칩니다.
모델 모드에서 호출 오류가 발생하면 데모 모드로 숨겨서 전환하지 않습니다.

두 문서를 섞지 않고 각각 청킹·벡터 검색합니다.

- `data/policy_corpus.md` → Policy MCP: POL 조항과 플랫폼 공식 요약
- `data/company-a-access-matrix.md` → Business MCP: 상한표·예외·승인 기준(3·4·7절만 RAG에 노출)
- 기본 검색은 로컬 문자 n-gram TF-IDF와 코사인 유사도입니다. 의미 임베딩 모델이라고 표시하지 않습니다.
- `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`를 지정하면 호환 `/embeddings` API를 사용합니다.
- 근거에 문서 ID·조항·버전·원본 파일 SHA-256을 남깁니다. 검색 결과가 약해도 필수 조항은 ID로 다시 읽습니다.
- 인사 사실·현재 권한·금액은 벡터 검색으로 추측하지 않고 DB에서 정확 조회합니다.

## 개발 디렉터리

```text
backend/                 Spring Security·요청 API·승인 규칙·outbox/inbox·DB 마이그레이션
frontend/                Vue 3 입력·담당자 작업함·승인 카드·처리 이력
python/unlockops/        LangGraph·두 MCP·정책 가드·RabbitMQ 워커
python/tests/            시나리오·상태 재개·실패·권한 제어 검증 코드
contracts/               공통 상태와 큐 메시지 계약
docs/                    아키텍처·평가표 대응·시연 절차
data/                    원본 정책·회사 접근 권한표
```

승인 후 설치·검증할 명령은 `docs/verification.md`를 참고하세요.
기존 서비스 실행 확인과 이번 코드 변경의 검증 결과를 구분해서 기록해야 합니다.

## 시연 데이터와 정책 해석

원본 MD는 초안 표시와 내용을 보존했습니다. 구현에서 선택한 해석·문서 간 차이는
`docs/policy-decisions.md`에 기록했습니다. 특히 일반 자원 부서장 승인과 직급별 상한은
회사 접근 권한표를 보충 규칙으로 사용합니다. 실제 회사 정책이 확정되었다는 뜻은 아닙니다.

이 코드는 단일 회사의 로컬 시연을 위한 프로토타입입니다. 모델 키를 넣고 LLM/임베딩 모드를 켜면
해당 서비스에 요청·규정 일부가 전송되고 API 비용이 발생할 수 있습니다.
