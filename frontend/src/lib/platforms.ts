import type { Platform } from '../api'

/** 플랫폼별 이름 · 색 · 아이콘(선 아이콘 path)과 입력 힌트. 시안과 같은 값. */
export const PLATFORMS: Record<Platform, { label: string; color: string; soft: string; icon: string; hint: string }> = {
  GITHUB: { label: 'GitHub', color: '#24292F', soft: '#EDEEF0', icon: 'M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 4l-3 16', hint: '저장소 이름 + 증상' },
  JIRA:   { label: 'Jira',   color: '#0B6B87', soft: '#E3F2F6', icon: 'M3 7h18v3a2 2 0 0 0 0 4v3H3v-3a2 2 0 0 0 0-4zM14 7v2M14 15v2', hint: '프로젝트 키 + 증상' },
  SLACK:  { label: 'Slack',  color: '#7A2E6E', soft: '#F5E8F2', icon: 'M4 5h16v11H10l-5 4v-4H4zM8 9h8M8 12h5', hint: '채널 이름 + 증상' },
  NOTION: { label: 'Notion', color: '#6B5A43', soft: '#F1ECE4', icon: 'M6 3h8l5 5v13H6zM14 3v5h5M9 13h7M9 17h5', hint: '페이지 이름 + 증상' },
}

export const PLATFORM_ORDER: Platform[] = ['GITHUB', 'JIRA', 'SLACK', 'NOTION']
