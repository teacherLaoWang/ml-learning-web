<script setup lang="ts">
/**
 * 播放头：时间轴 + 播放/暂停 + 单步 + 速度 + 重置 + 运行。
 * 用 rAF + 时间累加器推进 frame（不是 CSS 换色），页面不可见时自动停下。
 */
import { computed, ref, watch } from 'vue'
import { useDocumentVisible } from '../composables/useVisibility'
import { useRafLoop } from '../composables/useRafLoop'
import TermTip from './TermTip.vue'

const props = withDefaults(
  defineProps<{
    frame: number
    maxFrame: number
    playing: boolean
    speed: number
    busy?: boolean
    disabled?: boolean
    /** 已训练到第几步（单步超出时会去调 /step 继续训练） */
    fetchedSteps?: number
  }>(),
  { busy: false, disabled: false, fetchedSteps: 0 },
)

const emit = defineEmits<{
  'update:frame': [v: number]
  'update:playing': [v: boolean]
  'update:speed': [v: number]
  step: []
  reset: []
  run: []
}>()

const BASE_FPS = 14
const visible = useDocumentVisible()
const pos = ref(props.frame)
const canPlay = computed(() => props.playing && !props.busy && visible.value && pos.value < props.maxFrame)

useRafLoop((_t, dt) => {
  pos.value = Math.min(props.maxFrame, pos.value + dt * BASE_FPS * props.speed)
  const next = Math.floor(pos.value)
  if (next !== props.frame) emit('update:frame', next)
  if (pos.value >= props.maxFrame) emit('update:playing', false)
}, canPlay)

watch(
  () => props.frame,
  (v) => {
    if (Math.abs(v - pos.value) > 1) pos.value = v
  },
)
watch(
  () => props.maxFrame,
  (v) => {
    if (pos.value > v) {
      pos.value = v
      // 必须回写给父组件：否则 fill / 「frame x / y」继续读越界的 props.frame，
      // 会出现 149/59 这种读数与 250% 的进度条
      emit('update:frame', v)
      emit('update:playing', false)
    }
  },
)

function onScrub(ev: Event) {
  const v = Number((ev.target as HTMLInputElement).value)
  pos.value = v
  emit('update:frame', v)
  emit('update:playing', false)
}
function togglePlay() {
  if (props.playing) {
    emit('update:playing', false)
    return
  }
  if (pos.value >= props.maxFrame) {
    pos.value = 0
    emit('update:frame', 0)
  }
  emit('update:playing', true)
}
function reset() {
  pos.value = 0
  emit('update:playing', false)
  emit('update:frame', 0)
  emit('reset')
}
function stepOnce() {
  emit('update:playing', false)
  emit('step')
}
const shownFrame = computed(() => Math.min(props.frame, props.maxFrame))
const fillPct = computed(() => `${(shownFrame.value / Math.max(1, props.maxFrame)) * 100}%`)
const atEnd = computed(() => shownFrame.value >= props.maxFrame)
</script>

<template>
  <div class="player card-tight card">
    <div class="row between">
      <div class="row">
        <button class="btn btn-icon" :disabled="disabled" :aria-label="playing ? '暂停' : '播放'" @click="togglePlay">
          {{ playing ? '⏸' : '▶' }}
        </button>
        <button class="btn" :disabled="disabled || busy" @click="stepOnce">单步</button>
        <button class="btn" :disabled="disabled" @click="reset">重置</button>
        <button class="btn btn-primary" :disabled="disabled || busy" @click="emit('run')">
          {{ busy ? '跑…' : '运行' }}
        </button>
        <label class="row tiny muted">
          速度
          <select :value="speed" :disabled="disabled" @change="emit('update:speed', Number(($event.target as HTMLSelectElement).value))">
            <option :value="0.25">0.25×</option>
            <option :value="0.5">0.5×</option>
            <option :value="1">1×</option>
            <option :value="2">2×</option>
            <option :value="4">4×</option>
          </select>
        </label>
      </div>
      <div class="row tiny">
        <span class="chip mono">frame {{ frame }} / {{ maxFrame }}</span>
        <span v-if="fetchedSteps" class="chip">已训练 {{ fetchedSteps }} 步</span>
        <span v-if="!visible" class="chip chip-warn">页面不可见 · 已自动暂停</span>
        <span v-else-if="atEnd && !playing" class="chip chip-ok">已到末帧</span>
        <TermTip term="epoch" explain="一轮完整遍历训练集。这里的 frame 是优化步计数，不等同 epoch。">
          <span class="muted">frame ≠ epoch？</span>
        </TermTip>
      </div>
    </div>

    <input
      class="timeline slider"
      type="range"
      min="0"
      :max="maxFrame"
      :step="1"
      :value="frame"
      :style="{ '--fill': fillPct }"
      :disabled="disabled"
      aria-label="时间轴"
      @input="onScrub"
    />
  </div>
</template>

<style scoped>
.player {
  display: grid;
  gap: 6px;
  padding: 9px 12px 11px;
}
.between {
  justify-content: space-between;
}
.timeline {
  width: 100%;
}
</style>
