/** "오늘 10:12" · "어제 16:40" · "10월 15일" 형식 (시안 표기). */
export function shortWhen(value: string, now = new Date()) {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const hm = d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((day(now) - day(d)) / 86_400_000)
  if (diff === 0) return '오늘 ' + hm
  if (diff === 1) return '어제 ' + hm
  return `${d.getMonth() + 1}월 ${d.getDate()}일`
}
