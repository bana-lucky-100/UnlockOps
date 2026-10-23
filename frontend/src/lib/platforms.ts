import type { Platform } from '../api'

/** 플랫폼별 이름 · 색 · 아이콘(선 아이콘 path)과 입력 힌트. 시안과 같은 값. */
const BASE: Record<string, { label: string; color: string; soft: string; icon: string; hint: string }> = {
  GITHUB: { label: 'GitHub', color: '#24292F', soft: '#EDEEF0', icon: 'M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 4l-3 16', hint: '저장소 이름 + 증상' },
  JIRA:   { label: 'Jira',   color: '#0B6B87', soft: '#E3F2F6', icon: 'M3 7h18v3a2 2 0 0 0 0 4v3H3v-3a2 2 0 0 0 0-4zM14 7v2M14 15v2', hint: '프로젝트 키 + 증상' },
  SLACK:  { label: 'Slack',  color: '#7A2E6E', soft: '#F5E8F2', icon: 'M4 5h16v11H10l-5 4v-4H4zM8 9h8M8 12h5', hint: '채널 이름 + 증상' },
  NOTION: { label: 'Notion', color: '#6B5A43', soft: '#F1ECE4', icon: 'M6 3h8l5 5v13H6zM14 3v5h5M9 13h7M9 17h5', hint: '페이지 이름 + 증상' },
}


type PlatformInfo = { label: string; color: string; soft: string; icon: string; hint: string }
/**
 * Phase 2에서 추가된 SaaS 6개(규정 문서 v1.1 머리 표의 코드). 요청 입력(S-01) 칩에는 아직 넣지 않고,
 * 서버가 이 코드로 요청을 보내 올 때 화면이 깨지지 않고 이름을 보여 주는 용도다. Tableau 코드는 팀 확정 전이라 두 가지를 다 받는다.
 */
const DB_ICON = 'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3'
const CHART_ICON = 'M4 20V10M10 20V4M16 20v-7M22 20H2'
const EXTRA: Record<string, PlatformInfo> = {
  SNOWFLAKE:     { label: 'Snowflake',     color: '#11729E', soft: '#E3F3FB', icon: DB_ICON, hint: '웨어하우스 이름 + 용도' },
  DATABRICKS:    { label: 'Databricks',    color: '#B83A1C', soft: '#FDEBE6', icon: DB_ICON, hint: '작업 공간 · 노트북 이름 + 용도' },
  SALESFORCE:    { label: 'Salesforce',    color: '#0B5CAB', soft: '#E4F1FC', icon: 'M7 18a4 4 0 0 1-.6-7.96A5 5 0 0 1 16 8a4 4 0 1 1 1 10z', hint: '담당 고객 + 필요한 작업' },
  DATADOG:       { label: 'Datadog',       color: '#5B32A8', soft: '#EFE8FB', icon: CHART_ICON, hint: '서비스 이름 + 보려는 것' },
  TABLEAU_CLOUD: { label: 'Tableau Cloud', color: '#2C4E86', soft: '#E8EEF8', icon: CHART_ICON, hint: '프로젝트 이름 + 필요한 작업' },
  FIGMA:         { label: 'Figma',         color: '#B42D2D', soft: '#FDECEC', icon: 'M9 3h6a3 3 0 0 1 0 6H9zM9 9h6a3 3 0 1 1 0 6H9zM9 3a3 3 0 0 0 0 6M9 9a3 3 0 0 0 0 6M9 15a3 3 0 1 0 3 3v-3', hint: '파일 · 프로젝트 이름 + 필요한 작업' },
}
EXTRA.TABLEAU = EXTRA.TABLEAU_CLOUD
const UNKNOWN_ICON = 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8v5M12 16h.01'

/** 플랫폼 코드 → 화면 정보. 모르는 코드가 와도 화면이 깨지지 않고 코드 이름을 그대로 보여 준다. */
export function platformOf(code: string | null | undefined): PlatformInfo {
  const key = String(code ?? '')
  return BASE[key] ?? EXTRA[key]
    ?? { label: key || '알 수 없음', color: '#5B6178', soft: '#EEF0F5', icon: UNKNOWN_ICON, hint: '' }
}

/**
 * 권한 코드의 한국어 설명. 일반 직원·부서장이 코드만 보고는 무슨 권한인지 알기 어려워 제목에는 설명을, 코드는 작게 함께 보여 준다.
 * 문구는 규정 문서 v1.1(POL-03·04·05·08·09~14)의 표현을 옮겼다. 모르는 코드는 null(코드만 표시).
 */
const ROLE_TEXT: Record<string, Record<string, string>> = {
  GITHUB:        { read: '저장소 읽기', triage: '이슈 정리', write: '저장소 쓰기', seat: 'Copilot 좌석' },
  JIRA:          { viewer: '프로젝트 조회', developer: '프로젝트 작업' },
  SLACK:         { member: '채널 참여' },
  NOTION:        { 'can view': '페이지 읽기', 'can edit': '페이지 편집' },
  SNOWFLAKE:     { usage: '웨어하우스 이용' },
  DATABRICKS:    { 'can edit': '노트북 편집', 'can manage run': '작업 실행', 'can edit + can manage run': '노트북 편집 · 작업 실행' },
  SALESFORCE:    { read: '담당 고객 조회', edit: '담당 고객 조회 · 수정', 'read + edit': '담당 고객 조회 · 수정' },
  DATADOG:       { 'read only': '로그 · 대시보드 조회' },
  TABLEAU_CLOUD: { explorer: '대시보드 편집 · 게시' },
  FIGMA:         { full: '파일 편집', 'full seat': '파일 편집', 'can edit': '파일 편집' },
}
// v2(Phase 2) 카탈로그 권한 코드(data/phase2/seed.sql entitlements)
Object.assign(ROLE_TEXT.SNOWFLAKE, { analyst: '웨어하우스 분석 이용' })
Object.assign(ROLE_TEXT.DATABRICKS, { notebook_job_user: '노트북 · 작업 실행' })
Object.assign(ROLE_TEXT.SALESFORCE, { assigned_customer_editor: '담당 고객 조회 · 수정' })
Object.assign(ROLE_TEXT.DATADOG, { service_viewer: '서비스 로그 · 대시보드 조회' })
Object.assign(ROLE_TEXT.TABLEAU_CLOUD, { project_publisher: '대시보드 편집 · 게시' })
Object.assign(ROLE_TEXT.FIGMA, { editor_seat: '파일 편집 좌석' })
Object.assign(ROLE_TEXT.GITHUB, { copilot_seat: 'Copilot 좌석' })
Object.assign(ROLE_TEXT.NOTION, { editor: '페이지 편집', viewer: '페이지 읽기', reader: '페이지 읽기' })
ROLE_TEXT.TABLEAU = ROLE_TEXT.TABLEAU_CLOUD
export function roleText(platform: string | null | undefined, role: string | null | undefined): string | null {
  if (!role) return null
  return ROLE_TEXT[String(platform ?? '')]?.[role.trim().toLowerCase()] ?? null
}

/** 플랫폼 10개(v2). 이름 · 색은 위 표와 같다. */
export const PLATFORMS = { ...BASE, ...EXTRA } as Record<Platform, PlatformInfo>
export const PLATFORM_ORDER: Platform[] = ['GITHUB', 'JIRA', 'SLACK', 'NOTION']
export const PLATFORM_ORDER_V2: Platform[] = ['SNOWFLAKE', 'DATABRICKS', 'SALESFORCE', 'DATADOG', 'TABLEAU_CLOUD', 'FIGMA', 'GITHUB', 'JIRA', 'SLACK', 'NOTION']
