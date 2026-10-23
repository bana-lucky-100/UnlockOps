import { createRouter, createWebHistory } from 'vue-router'
import { ensureSession, homeOf } from './session'

declare module 'vue-router' {
  interface RouteMeta { role?: 'REQUESTER'|'APPROVER'; public?: boolean }
}

export const router = createRouter({
  history: createWebHistory(),
  // 화면이 바뀌면 맨 위에서 시작한다(주소에 #위치가 있으면 그 위치로).
  scrollBehavior: (to) => (to.hash ? { el: to.hash, behavior: 'smooth' } : { top: 0 }),
  routes: [
    // #29의 Phase 2 전용 화면(views/phase2/*)은 지우지 않고 연결만 뺐다. 지금은 아래 화면들이 v1 · v2 계정을 모두 받고,
    // 데이터는 lib/data.ts가 계정 세대에 맞춰 v2 API(phase2/api.ts)나 기존 API로 가져온다. 되돌릴 때는 이 줄들을 다시 넣으면 된다.
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/', component: () => import('./views/RequesterHome.vue'), meta: { role: 'REQUESTER' } },
    { path: '/approvals', component: () => import('./views/ApproverHome.vue'), meta: { role: 'APPROVER' } },
    // S-04 오늘의 회수 점검. 백엔드 API 전에는 VITE_UO_MOCK=true 로 목업 데이터를 본다.
    { path: '/revocations', component: () => import('./views/RevocationCheck.vue'), meta: { role: 'APPROVER' } },
    { path: '/requests', component: () => import('./views/MyRequests.vue'), meta: { role: 'REQUESTER' } },
    // 요청자(본인 요청)와 지정 승인자 모두 연다. 누가 볼 수 있는지는 서버가 정한다.
    { path: '/requests/:id', component: () => import('./views/RequestDetail.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const user = await ensureSession()
  if (to.meta.public) {
    // 이미 로그인했으면 로그인 화면 대신 기본 업무 화면으로.
    return to.path === '/login' && user ? homeOf(user) : true
  }
  if (!user) return { path: '/login', query: { next: to.fullPath } }
  // 메뉴 숨김은 편의일 뿐이고, 실제 차단은 서버(403)가 한다.
  if (to.meta.role && to.meta.role !== user.role) return homeOf(user)
  return true
})
