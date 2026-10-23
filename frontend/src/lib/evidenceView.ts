import type { Problem } from '../api'

/**
 * 승인자 화면의 '판단 근거'를 읽기 쉽게 정리한다 (판단 근거 원문은 승인자에게만).
 * 서버가 주는 근거는 Markdown 조각이라 표 기호(|, ---)와 굵게(**), 다음 절 제목(## …)이 섞여 있다.
 * 여기서 문서 이름을 붙이고, 조항은 번호 순으로, 표는 실제 표로 바꾸고, 요청과 관련 있는 행 · 열을 표시한다.
 */
export type EvidenceGroup = 'MATRIX' | 'POLICY' | 'OFFICIAL'
export interface Article { no: number | null; label: string; heading: string; text: string }
export interface Table { head: string[]; rows: string[][]; hitCol: number | null; hitRows: number[] }
export interface Doc { id: string; title: string; group: EvidenceGroup; articles: Article[]; tables: Table[]; notes: string[] }

const TITLES: Record<string, string> = {
  'A-ACCESS-03': '기본 상한표 (직무 × 직급 × 자원 종류)',
  'A-ACCESS-04': '예외 목록 (TF · 지정 부서 · 개인)',
  'A-ACCESS-07': '승인자 규칙',
  'POL-01': 'SaaS 권한 부여 기본 원칙',
  'POL-02': 'TF 구성원 권한 기준',
  'POL-03': 'GitHub 접근 권한 기준',
  'POL-04': 'Jira 프로젝트 역할 기준',
  'POL-05': 'Slack 채널 초대 기준',
  'POL-06': '유료 좌석 · 예산 기준',
  'POL-07': 'Admin · 보안 예외 기준',
  'POL-08': 'Notion 문서 보안 등급 기준',
  'GH-OFF-01': 'GitHub 조직 저장소 역할 구분',
  'GH-OFF-02': 'GitHub 팀을 통한 저장소 접근 관리',
  'JR-OFF-01': 'Jira 프로젝트 역할과 권한 스킴',
  'JR-OFF-02': 'Jira 프로젝트 미노출 트러블슈팅',
  'SL-OFF-01': 'Slack 채널 멤버 추가 방법',
  'SL-OFF-02': 'Slack 게스트 계정 유형 구분',
  'NT-OFF-01': 'Notion 페이지 공유 및 권한 수준',
  'P2-A-POLICY': 'A사 SaaS 권한 규정 (POL-06 · 승인 경로)',
  'P2-B-POLICY': 'B사 SaaS 권한 규정 (POL-06 · 승인 경로)',
}
export const GROUP_LABEL: Record<EvidenceGroup, string> = { MATRIX: '회사 권한표', POLICY: '사내 규정', OFFICIAL: 'SaaS 공식 도움말' }

// v2(Phase 2)는 회사별 규정 묶음(P2-A-POLICY 등)으로 온다. 사내 규정으로 분류한다.
const groupOf = (id: string): EvidenceGroup => id.startsWith('A-ACCESS') ? 'MATRIX' : id.startsWith('POL') || /^P2-[A-Z]+-POLICY$/.test(id) ? 'POLICY' : 'OFFICIAL'
const clean = (s: string) => s.replace(/\*\*/g, '').replace(/`/g, '').trim()

/** 요청자 직무 · 직급으로 상한표의 열 이름을 고른다. */
function columnHint(facts: Record<string, unknown> | undefined): string | null {
  if (!facts) return null
  if (facts.job_family === 'NON_DEV') return '비개발'
  if (facts.job_family !== 'DEV') return null
  return facts.grade === '사원' ? '개발 사원' : '개발 대리 이상'
}

/** 한 조각을 표 · 문단으로 나눈다. 다음 절 제목(## …)부터는 이 근거가 아니므로 버린다. */
function split(text: string): { tables: { head: string[]; rows: string[][] }[]; notes: string[] } {
  const lines = text.replace(/\r/g, '').split('\n')
  const tables: { head: string[]; rows: string[][] }[] = []
  const notes: string[] = []
  let cur: string[][] | null = null
  const flush = () => { if (cur && cur.length) tables.push({ head: cur[0], rows: cur.slice(1) }); cur = null }
  for (const [i, raw] of lines.entries()) {
    const line = raw.trim()
    if (/^#{1,6}\s/.test(line)) { if (i > 0) { flush(); break } else continue }
    if (line.startsWith('|')) {
      const cells = line.replace(/^\||\|$/g, '').split('|').map(clean)
      if (cells.every(c => /^:?-{2,}:?$/.test(c) || c === '')) continue
      ;(cur ??= []).push(cells)
      continue
    }
    flush()
    if (line && line !== '---') notes.push(clean(line))
  }
  flush()
  return { tables, notes }
}

/** "제2조(Write) TF 전용 …" → 번호 2, 제목 Write, 본문 */
function article(label: string, text: string): Article {
  const t = clean(text)
  const m = t.match(/^제\s*(\d+)\s*조\s*(?:\(([^)]*)\))?\s*(.*)$/s)
  const no = m ? Number(m[1]) : (label.match(/\d+/) ? Number(label.match(/\d+/)![0]) : null)
  return { no, label: m ? `제${m[1]}조` : label, heading: m?.[2]?.trim() ?? '', text: m ? m[3].trim() : t }
}

export function evidenceDocsOf(p: Problem, platformLabel: string | null): Doc[] {
  const list = Array.isArray(p.evidence) ? p.evidence : []
  const facts = list.find(e => e.kind === 'employee_facts') as Record<string, unknown> | undefined
  const col = columnHint(facts)
  const docs = new Map<string, Doc>()
  for (const e of list) {
    if (typeof e.doc_id !== 'string' || typeof e.text !== 'string' || !e.text.trim()) continue
    const doc = docs.get(e.doc_id) ?? { id: e.doc_id, title: TITLES[e.doc_id] ?? '', group: groupOf(e.doc_id), articles: [], tables: [], notes: [] }
    const label = typeof e.article === 'string' ? e.article : ''
    if (/^제\s*\d+\s*조/.test(e.text.trim()) || /^제\d+조$/.test(label)) {
      const a = article(label, e.text)
      if (!doc.articles.some(x => x.label === a.label && x.text === a.text)) doc.articles.push(a)
    } else {
      const { tables, notes } = split(e.text)
      for (const t of tables) {
        const hitCol = col ? t.head.findIndex(h => h.startsWith(col)) : -1
        const hitRows = platformLabel ? t.rows.map((r, i) => (r[0] === platformLabel ? i : -1)).filter(i => i >= 0) : []
        doc.tables.push({ ...t, hitCol: hitCol >= 0 ? hitCol : null, hitRows })
      }
      for (const n of notes) if (!doc.notes.includes(n)) doc.notes.push(n)
    }
    docs.set(e.doc_id, doc)
  }
  for (const d of docs.values()) d.articles.sort((a, b) => (a.no ?? 99) - (b.no ?? 99))
  const order: Record<EvidenceGroup, number> = { MATRIX: 0, POLICY: 1, OFFICIAL: 2 }
  return [...docs.values()].sort((a, b) => order[a.group] - order[b.group] || a.id.localeCompare(b.id))
}

/**
 * 승인자가 원문을 다 읽지 않아도 되도록, 규칙이 확인한 조건을 한 줄씩 결론으로 보여 준다.
 * 판정은 서버 규칙(rules.py)이 한다. 여기서는 서버가 준 사실(employee_facts · 요청 권한 · reason_code)만 다시 읽어 표시한다.
 * 데이터가 없는 조건은 만들지 않는다.
 */
export interface Check { ok: boolean; text: string; detail?: string; ref: string | null; info?: boolean }
const ROLE_RANK: Record<string, number> = { Read: 1, Write: 2, Viewer: 1, Developer: 2, 'Can view': 1, 'Can edit': 2, Member: 1, Seat: 1 }
const FORBIDDEN = new Set(['admin', 'owner', 'project admin', 'full access', '전체 액세스'])

export function checksOf(p: Problem, docs: Doc[]): Check[] {
  const list = Array.isArray(p.evidence) ? p.evidence : []
  const f = list.find(e => e.kind === 'employee_facts') as Record<string, unknown> | undefined
  const has = (id: string) => (docs.some(d => d.id === id) ? id : null)
  const role = String(p.requested_role ?? (p.plan as Record<string, unknown> | undefined)?.requested_role ?? '').trim()
  const max = f?.maximum_role ? String(f.maximum_role) : ''
  const out: Check[] = []
  if (role) {
    const bad = FORBIDDEN.has(role.toLowerCase())
    out.push({ ok: !bad, text: bad ? '관리자 권한이라 자동 부여할 수 없어요' : '관리자 권한(Admin · Owner) 요청이 아니에요', detail: bad ? role : undefined, ref: has('POL-07') })
  }
  if (role && max && ROLE_RANK[role] && ROLE_RANK[max]) {
    const ok = ROLE_RANK[role] <= ROLE_RANK[max]
    out.push({ ok, text: ok ? '요청 권한이 회사 권한표 상한 안이에요' : '요청 권한이 회사 권한표 상한을 넘어요', detail: `요청 ${role} · 상한 ${max}`, ref: has('A-ACCESS-03') })
  }
  if (f && (has('POL-02') || p.reason_code === 'NOT_TF_MEMBER')) {
    const ok = Boolean(f.tf_member)
    out.push({ ok, text: ok ? 'TF 명단에 있어요' : 'TF 명단에 없어요', ref: has('POL-02') })
  }
  if (f && 'current_role' in f) {
    out.push({ ok: true, text: f.current_role ? `지금 ${String(f.current_role)} 권한을 갖고 있어요` : '지금은 권한이 없어 새로 부여해요', ref: null, info: true })
  }
  return out
}
