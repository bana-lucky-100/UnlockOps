import test from 'node:test'
import assert from 'node:assert/strict'
import { evidenceDocsOf } from '../src/lib/evidenceView.ts'

const table = '설명 **굵게**\n\n| 플랫폼 | 자원 종류 | 개발 사원 | 개발 대리 이상 |\n|---|---|---|---|\n| GitHub | 일반 저장소 | Read | **Write** |\n| Jira | 일반 프로젝트 | Viewer | Developer |\n\n## 3. 다음 절 제목'
const p = { evidence: [
  { kind: 'employee_facts', grade: '사원', job_family: 'DEV' },
  { doc_id: 'POL-03', article: '제5조', text: '제5조(확인) 부여 후 다시 조회한다.' },
  { doc_id: 'POL-03', article: '제1조', text: '제1조(접근 단위) 팀 멤버십으로 부여한다.' },
  { doc_id: 'A-ACCESS-03', text: table },
] }

test('evidence is grouped matrix-first, articles sorted, markdown turned into a real table', () => {
  const docs = evidenceDocsOf(p, 'GitHub')
  assert.deepEqual(docs.map(d => d.id), ['A-ACCESS-03', 'POL-03'])
  assert.equal(docs[1].title, 'GitHub 접근 권한 기준')
  assert.deepEqual(docs[1].articles.map(a => [a.label, a.heading]), [['제1조', '접근 단위'], ['제5조', '확인']])
  const t = docs[0].tables[0]
  assert.deepEqual(t.head, ['플랫폼', '자원 종류', '개발 사원', '개발 대리 이상'])
  assert.equal(t.rows[0][3], 'Write')            // ** 제거
  assert.equal(t.hitCol, 2)                        // 요청자 열: 개발 사원
  assert.deepEqual(t.hitRows, [0])                 // 이 요청의 플랫폼 행
  assert.deepEqual(docs[0].notes, ['설명 굵게'])   // 다음 절 제목(## …)은 버림
})

test('checksOf: 규칙이 확인한 조건을 결론 문장으로 보여 준다', async () => {
  const { evidenceDocsOf, checksOf } = await import('../src/lib/evidenceView.ts')
  const p = { requested_role: 'Write', reason_code: 'ELIGIBLE', evidence: [
    { kind: 'employee_facts', grade: '대리', job_family: 'DEV', tf_member: true, current_role: null, maximum_role: 'Write' },
    { doc_id: 'A-ACCESS-03', text: '| 플랫폼 | 개발 대리 이상 |\n|---|---|\n| GitHub | Write |' },
    { doc_id: 'POL-02', text: '제1조(TF) TF 구성원만 TF 전용 자원에 접근한다.' },
    { doc_id: 'POL-07', text: '제1조(Admin 제외) Admin은 자동 부여하지 않는다.' },
  ] }
  const c = checksOf(p, evidenceDocsOf(p, 'GitHub'))
  assert.deepEqual(c.map(x => x.ok), [true, true, true, true])
  assert.equal(c[1].ref, 'A-ACCESS-03')
  assert.equal(c[1].detail, '요청 Write · 상한 Write')
  const over = checksOf({ ...p, requested_role: 'Admin' }, [])
  assert.equal(over[0].ok, false)
  assert.equal(over[0].ref, null)
})
