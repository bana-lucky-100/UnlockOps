/**
 * 시연 화면에서만 쓰는 페르소나 이름. 서버 시드(data/phase2/seed.sql)의 이름은 평가 데이터라 바꾸지 않고,
 * UX 산출물 · 발표의 페르소나(직원 김지성 · 부서장 김동빈 · IT 권한 관리 신형철)로 바꿔 보여 준다.
 * 사람을 구분하는 값(id)은 그대로라 권한 · 승인 판단에는 영향이 없다. 서버 이름이 바뀌면 이 표를 지운다.
 */
const PERSONA: Record<string, string> = {
  '김개발(A)': '김지성',
  '윤부장(A)': '김동빈',
  '송운영(A)': '신형철',
}
export function personaName(name: string): string
export function personaName(name: string | null | undefined): string | null | undefined
export function personaName(name: string | null | undefined) {
  return name == null ? name : PERSONA[name] ?? name
}

/**
 * 프로필 동그라미(이니셜 · 색). 로그인 화면의 계정 카드와 같은 글자 · 색을 헤더에서도 써서 "지금 누구로 들어왔는지"를 한눈에 맞춘다.
 * 시연 기본 계정은 로그인 카드와 같은 값, 그 밖의 계정은 이름(성 다음 글자)과 기본 파랑.
 */
export interface PersonaAvatar { initial: string; bg: string; fg: string }
const AVATAR: Record<string, PersonaAvatar> = {
  p2_a_requester: { initial: '지', bg: '#DDE2FF', fg: '#3B4BD8' },
  p2_a_head: { initial: '동', bg: '#EAE3FF', fg: '#6A45E0' },
  p2_a_operator: { initial: '형', bg: '#E1E4F5', fg: '#2B3480' },
}
export function personaAvatar(user: { login_id?: string; name: string }): PersonaAvatar {
  const known = user.login_id ? AVATAR[user.login_id] : undefined
  if (known) return known
  const name = personaName(user.name).replace(/\(.*\)$/, '').trim()
  // 이모지 · 결합 문자도 한 글자로 다루도록 코드 포인트 단위로 나눈다(charAt은 서로게이트 쌍을 자른다).
  const chars = Array.from(name)
  return { initial: (chars.length >= 3 ? chars[1] : chars[0]) ?? '', bg: '#DDE2FF', fg: '#3B4BD8' }
}
