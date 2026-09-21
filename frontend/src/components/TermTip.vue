<script setup lang="ts">
/**
 * 术语浮窗（§3.3：NN/SGD/MSE/Gini 等关键词统一走 TermTip）。
 * 硬要求 4：靠近视口边缘自动平移，上方放不下就翻到下方，永不裁切。
 */
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { lookupTerm } from '../composables/useGlossary'

const props = withDefaults(
  defineProps<{
    term: string
    full?: string
    explain?: string
    /** 强制显示（用于图例里的小圆点说明） */
    tint?: 'accent' | 'plain'
  }>(),
  { full: '', explain: '', tint: 'accent' },
)

const trigger = ref<HTMLElement | null>(null)
const pop = ref<HTMLElement | null>(null)
const open = ref(false)
const pinned = ref(false)
const popStyle = ref<Record<string, string>>({ left: '-9999px', top: '-9999px' })
const caretStyle = ref<Record<string, string>>({ left: '12px' })
const flip = ref<'up' | 'down'>('up')

const entry = computed(() => lookupTerm(props.term))
const title = computed(() => props.term || entry.value?.term || '')
const full = computed(() => props.full || entry.value?.full || '')
const explain = computed(() => props.explain || entry.value?.explain || '')
const keys = computed(() => entry.value?.keys ?? [])
const known = computed(() => !!entry.value || !!props.explain)

const MARGIN = 10
const GAP = 8

function place() {
  const t = trigger.value
  const p = pop.value
  if (!t || !p) return
  const vw = window.innerWidth
  const vh = window.innerHeight
  const rect = t.getBoundingClientRect()
  const w = p.offsetWidth
  const h = p.offsetHeight

  // 水平：先按触发器居中，再整体夹进视口（自动平移）
  let left = rect.left + rect.width / 2 - w / 2
  left = Math.max(MARGIN, Math.min(vw - w - MARGIN, left))

  // 垂直：默认放在上方；上方放不下翻到下方；两边都放不下就贴着能装下的那侧
  let top = rect.top - h - GAP
  flip.value = 'up'
  if (top < MARGIN) {
    top = rect.bottom + GAP
    flip.value = 'down'
  }
  if (top + h > vh - MARGIN) {
    if (vh - rect.bottom > rect.top) {
      top = Math.max(MARGIN, vh - h - MARGIN)
      flip.value = 'down'
    } else {
      top = MARGIN
      flip.value = 'up'
    }
  }
  popStyle.value = { left: `${Math.round(left)}px`, top: `${Math.round(top)}px` }
  const caret = rect.left + rect.width / 2 - left
  caretStyle.value = { left: `${Math.round(Math.max(12, Math.min(w - 12, caret)))}px` }
}

async function show() {
  if (!known.value) return
  open.value = true
  await nextTick()
  place()
}
function hide() {
  if (pinned.value) return
  open.value = false
}
function togglePin(ev?: Event) {
  ev?.preventDefault()
  if (!known.value) return
  if (pinned.value) {
    pinned.value = false
    open.value = false
    return
  }
  pinned.value = true
  void show()
}
function onKey(ev: KeyboardEvent) {
  if (ev.key === 'Escape' && open.value) {
    pinned.value = false
    open.value = false
  }
}
function reposition() {
  if (open.value) place()
}

onBeforeUnmount(() => {
  window.removeEventListener('scroll', reposition, true)
  window.removeEventListener('resize', reposition)
  document.removeEventListener('keydown', onKey)
})

function onEnter() {
  void show()
  window.addEventListener('scroll', reposition, true)
  window.addEventListener('resize', reposition)
  document.addEventListener('keydown', onKey)
}
function onLeave() {
  hide()
  if (!pinned.value) {
    window.removeEventListener('scroll', reposition, true)
    window.removeEventListener('resize', reposition)
    document.removeEventListener('keydown', onKey)
  }
}
</script>

<template>
  <span
    ref="trigger"
    class="term-tip"
    :class="{ 'is-known': known, pinned }"
    :tabindex="known ? 0 : -1"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
    @focus="onEnter"
    @blur="onLeave"
    @click="togglePin"
    @keydown.enter.prevent="togglePin"
  >
    <slot>{{ title }}</slot>
    <Teleport to="body">
      <div v-if="open" ref="pop" class="term-pop" :class="[`flip-${flip}`]" :style="popStyle">
        <span class="caret" :style="caretStyle" />
        <div class="tp-head">
          <b>{{ title }}</b>
          <em v-if="full">{{ full }}</em>
        </div>
        <div class="tp-body">{{ explain }}</div>
        <div v-if="keys.length" class="tp-keys">相关算法：{{ keys.join(' · ') }}</div>
      </div>
    </Teleport>
  </span>
</template>

<style scoped>
.term-tip {
  position: relative;
}
.term-tip.is-known {
  border-bottom: 1.5px dotted #93b4fb;
  cursor: help;
}
.term-tip.pinned {
  background: #e8efff;
  border-radius: 4px;
}
.term-pop {
  pointer-events: none;
}
.term-pop .caret {
  position: absolute;
  width: 9px;
  height: 9px;
  background: var(--panel);
  border: 1px solid var(--line);
  transform: rotate(45deg);
}
.term-pop.flip-up .caret {
  bottom: -5.5px;
  border-top-color: transparent;
  border-left-color: transparent;
}
.term-pop.flip-down .caret {
  top: -5.5px;
  border-bottom-color: transparent;
  border-right-color: transparent;
}
.tp-head {
  display: flex;
  gap: 7px;
  align-items: baseline;
  flex-wrap: wrap;
  margin-bottom: 3px;
}
.tp-head b {
  font-size: 13.5px;
}
.tp-head em {
  font-style: normal;
  color: var(--muted);
  font-size: 11.5px;
}
.tp-body {
  color: var(--ink-2);
}
.tp-keys {
  margin-top: 5px;
  font-size: 11.5px;
  color: var(--muted);
}
</style>
