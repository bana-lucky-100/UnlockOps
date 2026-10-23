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

/**
 * 로그아웃은 서버 세션이 실제로 끝났을 때만 화면에서도 로그아웃으로 처리한다.
 * - 401: 서버 세션이 이미 끝남 → 로그아웃된 것으로 본다.
 * - 403: 보안 토큰(CSRF)이 낡은 경우라 세션은 살아 있을 수 있다 → 토큰을 새로 받아 한 번 더 시도한다.
 * - 그 밖의 실패: 세션이 남아 있으니 화면도 로그인 상태로 두고 오류를 알린다.
 */
export async function logout() {
  const post = () => api('/auth/logout', {method: 'POST'})
  try {
    await post()
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) {
      await refreshCsrf()
      try { await post() } catch (e2) { if (!(e2 instanceof ApiError && e2.status === 401)) throw e2 }
    } else if (!(e instanceof ApiError && e.status === 401)) {
      throw e
    }
  }
  currentUser.value = null
  await refreshCsrf().catch(() => {})
}

/** 역할별 첫 화면: 요청자는 홈, 승인자는 승인함. */
export function homeOf(user: User) {
  if (user.workflow_version === 2) return '/access'
  return user.role === 'APPROVER' ? '/approvals' : '/'
}
