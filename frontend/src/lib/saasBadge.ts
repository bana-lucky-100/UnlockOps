/**
 * 회수 점검 표에서 SaaS를 한눈에 구분하기 위한 이니셜 배지 색. 실제 로고(상표)는 쓰지 않는다.
 * 키는 화면에 보이는 SaaS 이름. 없는 이름은 기본 색으로 표시한다.
 */
const BADGE: Record<string, { mono: string; bg: string; fg: string }> = {
  'Snowflake':      { mono: 'Sf', bg: '#E3F3FB', fg: '#11729E' },
  'Databricks':     { mono: 'Db', bg: '#FDEBE6', fg: '#B83A1C' },
  'Salesforce':     { mono: 'Sa', bg: '#E4F1FC', fg: '#0B5CAB' },
  'Datadog':        { mono: 'Dd', bg: '#EFE8FB', fg: '#5B32A8' },
  'Tableau Cloud':  { mono: 'Tb', bg: '#E8EEF8', fg: '#2C4E86' },
  'Figma':          { mono: 'Fg', bg: '#FDECEC', fg: '#B42D2D' },
  'GitHub Copilot': { mono: 'Co', bg: '#EDEEF0', fg: '#24292F' },
  'GitHub':         { mono: 'Gh', bg: '#EDEEF0', fg: '#24292F' },
  'Jira':           { mono: 'Ji', bg: '#E3F2F6', fg: '#0B6B87' },
  'Slack':          { mono: 'Sl', bg: '#F5E8F2', fg: '#7A2E6E' },
  'Notion':         { mono: 'No', bg: '#F1ECE4', fg: '#6B5A43' },
}
export function saasBadge(name: string) {
  return BADGE[name] ?? { mono: name.slice(0, 2), bg: '#EEF0FF', fg: '#2F3DB8' }
}
