import type { Platform } from '../api'

/**
 * 요청 문장에서 플랫폼을 찾아 제안한다(플랫폼이 10개라 칩을 먼저 고르게 하면 불편했다).
 * 브랜드 이름(영문 · 한글 표기)을 먼저 보고, 하나도 없을 때만 흔한 자원 단어(웨어하우스, 저장소, 채널 …)로 추측한다.
 * 여러 개가 걸리면 고르게 하고(요청 1건 = 플랫폼 1개), 사용자가 직접 고른 값은 덮어쓰지 않는다. 최종 판단은 서버가 다시 한다.
 */
const BRAND: [Platform, RegExp][] = [
  ['SNOWFLAKE', /snow\s*flake|스노우?플레이크/i],
  ['DATABRICKS', /data\s*bricks|데이터\s*브릭스/i],
  ['SALESFORCE', /sales\s*force|세일즈\s*포스/i],
  ['DATADOG', /data\s*dog|데이터\s*독/i],
  ['TABLEAU_CLOUD', /tableau|태블로|타블로/i],
  ['FIGMA', /figma|피그마/i],
  ['GITHUB', /git\s*hub|깃\s*허브|copilot|코파일럿/i],
  ['JIRA', /jira|지라/i],
  ['SLACK', /slack|슬랙/i],
  ['NOTION', /notion|노션/i],
]
const HINT: [Platform, RegExp][] = [
  ['SNOWFLAKE', /웨어하우스|warehouse/i],
  ['GITHUB', /저장소|레포|repo/i],
  ['SLACK', /채널/],
  ['NOTION', /위키/],
]

export function guessPlatforms(text: string): Platform[] {
  const t = text ?? ''
  const brands = BRAND.filter(([, re]) => re.test(t)).map(([p]) => p)
  if (brands.length) return brands
  return HINT.filter(([, re]) => re.test(t)).map(([p]) => p)
}
