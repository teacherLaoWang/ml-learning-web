/** 通用 rAF 循环：由外部 active 决定真的启停（不是空转）。 */
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

export function useRafLoop(cb: (time: number, dt: number) => void, active: Ref<boolean>) {
  let raf: number | null = null
  let last = 0
  const time = ref(0)

  const frame = (ts: number) => {
    const dt = last ? Math.min(0.05, (ts - last) / 1000) : 0.016
    last = ts
    time.value += dt
    cb(time.value, dt)
    raf = requestAnimationFrame(frame)
  }
  const start = () => {
    if (raf !== null || typeof requestAnimationFrame === 'undefined') return
    last = 0
    raf = requestAnimationFrame(frame)
  }
  const stop = () => {
    if (raf !== null) cancelAnimationFrame(raf)
    raf = null
    last = 0
  }

  watch(active, (on) => (on ? start() : stop()))
  onMounted(() => {
    if (active.value) start()
  })
  onBeforeUnmount(stop)

  return { time, start, stop }
}
