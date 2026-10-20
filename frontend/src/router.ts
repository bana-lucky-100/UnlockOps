import { createRouter, createWebHistory } from 'vue-router'
import { ensureSession, homeOf } from './session'

declare module 'vue-router' {
  interface RouteMeta { role?: 'REQUESTER'|'APPROVER'; public?: boolean }
}

export const router = createRouter({
  history: createWebHistory(),
  // 왼쪽 메뉴의 '내 요청'(/#mine)은 홈 안의 목록 위치로 이동한다.
  scrollBehavior: (to) => (to.hash ? { el: to.hash, behavior: 'smooth' } : { top: 0 }),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/', component: () => import('./views/RequesterHome.vue'), meta: { role: 'REQUESTER' } },
    { path: '/approvals', component: () => import('./views/ApproverHome.vue'), meta: { role: 'APPROVER' } },
    // 요청자(본인 요청)와 지정 승인자 모두 연다. 누가 볼 수 있는지는 서버가 정한다.
    { path: '/requests/:id', component: () => import('./views/RequestDetail.vue') },
    // 기존 단일 화면. 새 화면이 모두 옮겨지면 지운다 (#6).
    { path: '/console', component: () => import('./views/LegacyConsole.vue'), meta: { public: true } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const user = await ensureSession()
  if (to.meta.public) {
    // 이미 로그인했으면 로그인 화면 대신 역할별 첫 화면으로.
    return to.path === '/login' && user ? homeOf(user) : true
  }
  if (!user) return { path: '/login', query: { next: to.fullPath } }
  // 메뉴 숨김은 편의일 뿐이고, 실제 차단은 서버(403)가 한다.
  if (to.meta.role && to.meta.role !== user.role) return homeOf(user)
  return true
})
