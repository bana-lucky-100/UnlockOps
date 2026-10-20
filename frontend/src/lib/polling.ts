import { onBeforeUnmount, onMounted } from 'vue'

/**
 * 명세: SSE 대신 2.5초마다 다시 조회한다.
 * 탭이 가려져 있으면 쉬고, 앞선 조회가 끝나기 전에는 겹쳐 부르지 않는다.
 * tick이 false를 돌려주면(더 볼 게 없음) 멈춘다.
 */
export function usePolling(tick: () => Promise<boolean | void>, intervalMs = 2500) {
  let timer: ReturnType<typeof setTimeout> | undefined
  let running = false
  let stopped = false

  async function run() {
    if (stopped) return
    if (document.hidden) { schedule(); return }
    if (running) return
    running = true
    try {
      const more = await tick()
      if (more === false) { stopped = true; return }
    } catch {
      // 일시 오류는 다음 주기에 다시 시도한다. 화면 안내는 tick 쪽에서 한다.
    } finally {
      running = false
    }
    schedule()
  }
  function schedule() {
    clearTimeout(timer)
    if (!stopped) timer = setTimeout(run, intervalMs)
  }
  function restart() { stopped = false; clearTimeout(timer); void run() }
  const onVisible = () => { if (!document.hidden && !stopped) restart() }

  onMounted(() => { document.addEventListener('visibilitychange', onVisible); void run() })
  onBeforeUnmount(() => { stopped = true; clearTimeout(timer); document.removeEventListener('visibilitychange', onVisible) })

  return { restart }
}
