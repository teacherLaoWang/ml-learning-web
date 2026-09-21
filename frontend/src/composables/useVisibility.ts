/**
 * 可见性/帧驱动 composable。
 * 硬要求 3：页面不可见（切标签、锁屏）或面板滚出视口时，必须真的停下来，不烧 CPU。
 */
import { computed, onBeforeUnmount, onMounted, ref, type ComputedRef, type Ref } from 'vue'

export function useDocumentVisible(): Ref<boolean> {
  const visible = ref(typeof document === 'undefined' ? true : document.visibilityState !== 'hidden')
  const onChange = () => {
    visible.value = document.visibilityState !== 'hidden'
    document.body.classList.toggle('is-hidden', !visible.value)
  }
  onMounted(() => {
    document.addEventListener('visibilitychange', onChange)
    window.addEventListener('pagehide', onChange)
    window.addEventListener('pageshow', onChange)
    onChange()
  })
  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onChange)
    window.removeEventListener('pagehide', onChange)
    window.removeEventListener('pageshow', onChange)
  })
  return visible
}

/** 元素是否在视口内（threshold 0.02：只要有一点点可见就继续画） */
export function useElementInBox(el: Ref<HTMLElement | null | undefined>): Ref<boolean> {
  const inView = ref(true)
  let io: IntersectionObserver | null = null
  onMounted(() => {
    const node = el.value
    if (!node || typeof IntersectionObserver === 'undefined') return
    io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) inView.value = e.isIntersecting
      },
      { root: null, threshold: 0.02 },
    )
    io.observe(node)
  })
  onBeforeUnmount(() => {
    io?.disconnect()
    io = null
  })
  return inView
}

/** 合成「可以动画」的条件：文档可见 && 元素在视口内 */
export function useAnimActive(el: Ref<HTMLElement | null | undefined>): { active: ComputedRef<boolean>; visible: Ref<boolean> } {
  const visible = useDocumentVisible()
  const inView = useElementInBox(el)
  return { active: computed(() => visible.value && inView.value), visible }
}
