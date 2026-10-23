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
