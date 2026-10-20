import { ref } from 'vue'
import { api, ApiError, refreshCsrf, type User } from './api'

/** 로그인한 사용자. 세션 쿠키가 기준이고, 화면은 /auth/me로 확인한 값만 믿는다. */
export const currentUser = ref<User|null>(null)
let checked = false

/** 새로고침 직후 한 번만 서버에 세션을 확인한다. 401이면 비로그인으로 둔다. */
export async function ensureSession(): Promise<User|null> {
  if (checked) return currentUser.value
  try {
    currentUser.value = await api<User>('/auth/me')
    checked = true
  } catch (e) {
    currentUser.value = null
    // 401은 '로그인 안 됨'으로 확정. 서버가 꺼져 있는 등 다른 오류는 다음 이동 때 다시 확인한다.
    if (e instanceof ApiError && e.status === 401) checked = true
  }
  return currentUser.value
}

export async function login(loginId: string, password: string): Promise<User> {
  const user = await api<User>('/auth/login', {method: 'POST', body: JSON.stringify({loginId, password})})
  // 로그인하면 세션이 새로 만들어지므로 CSRF 토큰도 다시 받는다.
  await refreshCsrf()
  currentUser.value = user
  checked = true
  return user
}

/** 서버 세션이 이미 끝났어도(401 · 403) 화면에서는 반드시 로그아웃되게 한다. */
export async function logout() {
  try {
    await api('/auth/logout', {method: 'POST'})
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 401 || e.status === 403))) throw e
  } finally {
    currentUser.value = null
  }
  await refreshCsrf().catch(() => {})
}

/** 역할별 첫 화면: 요청자는 홈, 승인자는 승인함. */
export function homeOf(user: User) {
  return user.role === 'APPROVER' ? '/approvals' : '/'
}
