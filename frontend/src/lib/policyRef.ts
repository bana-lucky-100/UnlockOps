/**
 * 서버 article 원문("POL-06 | COMMON | v1.1 | 제5조(회수 점검)")을 화면용 짧은 이름("POL-06 제5조(회수 점검)")으로.
 * 원문 ID와 조항만 남기고 플랫폼 · 버전은 뺀다. 형식이 다르면 그대로 둔다.
 */
export function shortArticle(article: string): string {
  const parts = article.split('|').map(s => s.trim()).filter(Boolean)
  return parts.length >= 2 ? `${parts[0]} ${parts[parts.length - 1]}` : article.trim()
}

/** 회수 근거 목록 → 사내 규정(POL-*) 조항만 중복 없이. 규정 조항이 하나도 없으면 첫 근거 하나만. */
export function policyRefs(evidence: { article: string }[]): string {
  const all = evidence.map(e => shortArticle(e.article))
  const pol = [...new Set(all.filter(a => a.startsWith('POL-')))]
  return (pol.length ? pol : all.slice(0, 1)).join(' · ')
}
