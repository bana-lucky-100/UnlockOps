import type { Platform } from '../api'

/**
 * 요청 문장에서 플랫폼을 찾아 제안한다(플랫폼이 10개라 칩을 먼저 고르게 하면 불편했다).
 * 띄어쓰기 · 대소문자를 무시하고 비교한다("스노우 플레이크", "Snow Flake"도 같은 말).
 * 브랜드 이름(영문 · 흔한 한글 표기 · 줄임말)을 먼저 보고, 하나도 없을 때만 흔한 자원 단어(웨어하우스, 저장소 …)로 추측한다.
 * 여러 개가 걸리면 고르게 하고(요청 1건 = 플랫폼 1개), 사용자가 직접 고른 값은 덮어쓰지 않는다. 최종 판단은 서버가 다시 한다.
 */
const BRAND: [Platform, string[]][] = [
  ['SNOWFLAKE', ['snowflake', '스노우플레이크', '스노플레이크', '스노우플래이크', '스노우플레익']],
  ['DATABRICKS', ['databricks', '데이터브릭스', '데이타브릭스', '데브릭스', '브릭스']],
  ['SALESFORCE', ['salesforce', '세일즈포스', '세일즈포즈', 'sfdc']],
  ['DATADOG', ['datadog', '데이터독', '데이타독', '데독']],
  ['TABLEAU_CLOUD', ['tableau', '태블로', '타블로', '테블로', '테이블로', '태블루']],
  ['FIGMA', ['figma', '피그마', '피그마디자인']],
  ['GITHUB', ['github', 'git', '깃허브', '깃헙', '기트허브', '깃허브코파일럿', 'copilot', '코파일럿', '코파일롯', '코필럿']],
  ['JIRA', ['jira', '지라', '쥐라', '지이라']],
  ['SLACK', ['slack', '슬랙', '슬렉']],
  ['NOTION', ['notion', '노션', '노숀']],
]
const HINT: [Platform, string[]][] = [
  ['SNOWFLAKE', ['웨어하우스', 'warehouse']],
  ['GITHUB', ['저장소', '레포', 'repo', '리포지토리']],
  ['SLACK', ['채널']],
  ['NOTION', ['위키']],
  ['DATADOG', ['로그모니터링', '모니터링대시보드']],
]

/** 띄어쓰기 · 하이픈 · 대소문자를 지운 비교용 문자열. */
const squash = (s: string) => s.toLowerCase().replace(/[\s\-_.·]/g, '')

function hits(table: [Platform, string[]][], raw: string, flat: string): Platform[] {
  // 'git'처럼 짧은 영문 줄임말은 다른 단어 속에 들어 있을 수 있어(digital 등) 영문 단어 경계로만 본다.
  return table.filter(([, words]) => words.some(w => /^[a-z]{1,4}$/.test(w) ? new RegExp(`(^|[^a-z])${w}([^a-z]|$)`).test(raw) : flat.includes(w)))
    .map(([p]) => p)
}

export function guessPlatforms(text: string): Platform[] {
  const raw = (text ?? '').toLowerCase()
  const flat = squash(raw)
  const brands = hits(BRAND, raw, flat)
  return brands.length ? brands : hits(HINT, raw, flat)
}
