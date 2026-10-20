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

/** "방금" · "18분 전" · "2시간 전", 하루가 넘으면 shortWhen 형식. 승인 대기 경과 시간에 쓴다. */
export function ago(value: string, now = new Date()) {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const min = Math.floor((now.getTime() - d.getTime()) / 60_000)
  if (min < 1) return '방금'
  if (min < 60) return `${min}분 전`
  if (min < 24 * 60) return `${Math.floor(min / 60)}시간 전`
  return shortWhen(value, now)
}
