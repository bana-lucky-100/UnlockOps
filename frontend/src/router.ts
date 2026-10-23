import { createRouter, createWebHistory } from 'vue-router'
import { ensureSession, homeOf } from './session'

declare module 'vue-router' {
  interface RouteMeta { role?: 'REQUESTER'|'APPROVER'; public?: boolean; phase2?: boolean }
}

export const router = createRouter({
  history: createWebHistory(),
  // 화면이 바뀌면 맨 위에서 시작한다(주소에 #위치가 있으면 그 위치로).
  scrollBehavior: (to) => (to.hash ? { el: to.hash, behavior: 'smooth' } : { top: 0 }),
  routes: [
    { path: '/access', component: () => import('./views/phase2/AccessList.vue'), meta: { phase2: true } },
    { path: '/access/new', component: () => import('./views/phase2/AccessNew.vue'), meta: { phase2: true } },
    { path: '/access/:id', component: () => import('./views/phase2/AccessDetail.vue'), meta: { phase2: true } },
    { path: '/reclaim', component: () => import('./views/phase2/ReclaimHome.vue'), meta: { phase2: true } },
    { path: '/reclaim/runs/:id', component: () => import('./views/phase2/ReclaimRun.vue'), meta: { phase2: true } },
    { path: '/reclaim/targets/:id', component: () => import('./views/phase2/ReclaimTarget.vue'), meta: { phase2: true } },
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/', component: () => import('./views/RequesterHome.vue'), meta: { role: 'REQUESTER' } },
    { path: '/approvals', component: () => import('./views/ApproverHome.vue'), meta: { role: 'APPROVER' } },
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
  if (!!to.meta.phase2 !== (user.workflow_version !== 1)) return homeOf(user)
  // 메뉴 숨김은 편의일 뿐이고, 실제 차단은 서버(403)가 한다.
  if (to.meta.role && to.meta.role !== user.role) return homeOf(user)
  return true
})
