# Frontend

A1 담당입니다. Vue 3, TypeScript, Vite를 사용하며 Node 22.12 이상을 권장합니다.
접수·본인 상태 조회·승인 카드·처리 이력·내 승인 현황이 구현되어 있습니다.
API는 세션 쿠키와 CSRF를 사용하며 개발 서버는 /api를 localhost:8080으로 프록시합니다.

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
