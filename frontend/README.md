# Frontend

A1 담당입니다. Vue 3, TypeScript, Vite를 사용하며 Node 22.12 이상을 권장합니다.
접수·본인 상태 조회·승인 카드·처리 이력·내 승인 현황이 구현되어 있습니다.
API는 세션 쿠키와 CSRF를 사용하며 개발 서버는 /api를 localhost:8080으로 프록시합니다.

`VITE_UO_MOCK=true`는 일부 비용·회수 화면을 모의 데이터로 표시하는 선택 설정이며 기본은 꺼져 있습니다.
설정은 `frontend/.env.local`에 두고 Vite를 재시작하거나 재빌드합니다. 루트 `.env`는 읽지 않으며 `VITE_*` 값은 브라우저에 공개됩니다. 전체 설정 경계는 [환경변수 안내](../docs/environment.md)를 참고하세요.

이 폴더에서 실행합니다.

```sh
npm ci
npm run dev
npm test
npm run build
```

접수는 `views/RequesterHome.vue`가 `composables/useProblemSubmission.ts`의 `submitProblem(input)`을 호출합니다.
composable이 로그인 사용자 범위, `Idempotency-Key` 헤더와 API 호출, 사용자 변경 후 이전 응답·오류 무시를 담당합니다.
뷰는 폼 입력 검증·전송 표시·성공 후 상세 이동을 담당하며, `App.vue`는 라우터 화면만 표시합니다.
`problemSubmission.ts`의 `ProblemSubmission`은 사용자와 전송 본문별 키 수명을 관리합니다.
composable 모듈에서 인스턴스를 공유하므로 화면 이동·재진입에도 페이지 내 키를 유지합니다.
응답 유실·오류 후 같은 접수를 재시도하면 같은 키를 사용하며, 같은 페이지의 동시 제출은 하나의 POST를 공유합니다.
수락 응답을 확인하면 키를 정리합니다. 이후 목록 조회 실패는 접수 실패로 되돌리지 않으며, 새 제출·다른 본문에는 새 키를 사용합니다.

같은 탭의 새로고침 복구를 위해 sessionStorage에는 사용자별 pending 키와 본문 SHA-256만 보관합니다.
원본 문제 내용·비밀번호·토큰은 이 기록에 저장하지 않습니다. 폼 초안 복원이나 탭 간 접수 통합 기능은 아닙니다.
저장소가 차단되면 페이지 내 메모리 키를 사용하며, 탭 종료·저장소 차단 시 새로고침 이후의 키 복구는 보장하지 않습니다.
Web Crypto를 사용하므로 HTTPS 또는 localhost의 보안 컨텍스트에서 실행합니다.

`npm test`는 Node의 테스트 러너와 TypeScript 타입 제거 기능으로 키 수명·재시도·동시 제출·저장소 오류를 검증합니다.
회귀 테스트는 기존 Vue/TypeScript 컴파일러로 실제 SFC의 `send()`·접수 composable·API 클라이언트를 실행해
접수 키·CSRF 헤더, 실패 후 화면 재진입, 수락 후 이동 실패, 사용자 변경을 검증합니다. 라우터·주기 조회·HTTP는 대체하며 브라우저 DOM 테스트는 아닙니다.
별도 테스트 의존성을 추가하지 않으며 Node 22.12 이상을 사용합니다. backend의 기존 키 없는 클라이언트에는 멱등성이 적용되지 않습니다.

Docker 화면은 localhost:8088, Vite 개발 화면은 localhost:5173입니다.
백엔드 시작 순서는 [디버깅 안내](../docs/debugging.md)를 참고하세요.

안내 성공은 서버가 반환한 `status=DONE`, `result_type=GUIDANCE`로 판별합니다. 사유 코드나 문구로 완료 상태를 추측하지 않습니다.
화면에서는 초록색 `안내 완료`로 표시하고, 끝난 요청 및 최근 처리 목록에 포함하며 해당 요청의 자동 조회를 종료합니다.
안내 완료 상세에서 요청자에게는 API의 `diagnosis`만 표시하고, 긴 안내 본문(`proposal`)은 승인자에게만 표시합니다.
권한 부여 단계 대신 접수 → 진단 → 안내 제공을 보여줍니다.
권한 반영 완료는 `DONE / result_type=ACCESS_VERIFIED / verification_ok=true`로 구분합니다. 구 감사 이벤트만 호환 표시하며, 현재 요청의 완료 여부는 새 계약만 사용합니다.
`guidanceCompletion.test.mjs`는 이 응답의 완료 분류·본문 표시·진행 기록과 실제 검토 필요 상태의 구분을 검증합니다.

## Phase 2 화면

기본 로그인 카드는 A사 직원(`p2_a_requester`)·1차 승인자(`p2_a_head`)·권한 담당자(`p2_a_operator`)입니다.
카드를 누르거나 회사·담당 역할을 선택하면 즉시 로그인합니다. 화면에 시연 비밀번호를 저장하지 않으며,
`POST /api/auth/demo-login`에 계정 ID만 전달하고 서버가 시연 설정과 허용 계정을 확인한 뒤 일반 인증·세션 발급을 수행합니다.
비밀번호를 입력하면 기존 `POST /api/auth/login`을 사용합니다. 시연 계정은 비밀번호가 비어 있어도 로그인 버튼으로 진입할 수 있습니다.
로그인하면 `/access`로 진입하며, 별도의 버전 선택 없이 10개 플랫폼 요청·승인 화면을 사용합니다.
회사·담당 역할 선택에서 A/B사 직원·승인자·권한 담당자·IT 총괄로 전환할 수 있습니다.
기본 화면은 Phase 2이며, 서버가 명시적으로 `workflow_version=1`을 반환하는 기존 LEGACY 계정만 이전 화면과 호환합니다.
기존 계정의 소속·권한·요청을 새 회사로 자동 이관하지 않습니다.
화면은 `src/views/phase2`, 공통 컴포넌트는 `src/components/phase2`, API·표시 규칙·접수 키는 `src/phase2`에 있습니다.

| 경로 | 기능 |
|---|---|
| /access | 내 요청·내 승인 차례·허용된 전체 목록 |
| /access/new | 10개 플랫폼·자원/권한 선택·분석 요청 |
| /access/:id | 보고서·정책·비용·단계별 승인/반려/보류·재분석 |
| /reclaim | 범위별 점검·후보·본인 알림 읽음 |
| /reclaim/runs/:id | 실행 상태·전체/유지/제외/미확인 판정 |
| /reclaim/targets/:id | 후보 근거·비용 상세 |

회수 메뉴 표시에는 서버의 can_reclaim을 사용하며 API ACL을 대신하지 않습니다.
현재 지정 승인자만 버튼을 볼 수 있고 승인·반려·보류에는 조회한 plan_hash와 plan_version을 expected_plan_hash와 expected_plan_version으로 함께 보냅니다.
승인 대기 응답에 유효한 버전이 없으면 결정을 허용하지 않습니다. 보류·재개 후에는 해시가 같아도 이전 회차의 결정이 409로 거절됩니다.
409·응답 유실 후에는 서버를 다시 조회하며 승인을 자동 재전송하지 않습니다.
회수 DONE은 점검 완료이고, 비용 UNKNOWN은 미확인입니다. 실제 권한 말소·환입은 하지 않습니다.
요청·점검 시작의 재시도 키는 사용자와 작업별로 분리하여 보관하며 원문은 sessionStorage에 저장하지 않습니다.

Compose 시연 환경은 [mock seed 안내](../data/phase2/README.md)의 초기 데이터를 기동 시 준비합니다.
개별 백엔드 실행에서는 DEMO_ENABLED=true와 DEMO_SEED_PATH를 설정하거나 초기 데이터를 수동 적용해야 합니다. DEMO_PHASE2_SEED_PATH는 이전 Spring 호환 별칭입니다.
A사 승인 경로는 p2_a_requester → p2_a_head → p2_a_operator이며, B사 통합 회수 점검 계정은 p2_b_it_head입니다.

신규 핵심 테스트는 phase2.test.mjs 3건입니다. 지정 버전 의존성 설치·브라우저·전체 스택 검증의 제한과 대체 검증 결과는
[IMPLEMENTATION.md](../IMPLEMENTATION.md)의 4단계 검증 범위를 확인하세요. 이번 작업에서는 package.json/lockfile을 변경하지 않았습니다.
