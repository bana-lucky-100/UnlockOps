# Frontend

A1 담당입니다. Vue 3, TypeScript, Vite를 사용하며 Node 22.12 이상을 권장합니다.
접수·본인 상태 조회·승인 카드·처리 이력·소속 부서 요약이 구현되어 있습니다.
API는 세션 쿠키와 CSRF를 사용하며 개발 서버는 /api를 localhost:8080으로 프록시합니다.

이 폴더에서 실행합니다.

```sh
npm ci
npm run dev
npm run build
```

Docker 화면은 localhost:8088, Vite 개발 화면은 localhost:5173입니다.
백엔드 시작 순서는 [디버깅 안내](../docs/debugging.md)를 참고하세요.
