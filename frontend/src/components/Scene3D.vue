<script setup lang="ts">
/**
 * 3D 通用容器：透视相机 + OrbitControls + 环境光/方向光 + 图例 + 自动暂停。
 * 具体画什么由子组件（Surface3D / Cloud3D / Vector3D）通过 ENGINE_REF_KEY 挂进场景。
 */
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { SceneEngine } from '../three/engine'
import { useAnimActive } from '../composables/useVisibility'
import type { LegendItem } from '../types'

const props = withDefaults(
  defineProps<{
    title?: string
    hint?: string
    /** 固定角落图例：不与主体重叠 */
    legend?: LegendItem[]
    /** 关掉内在动画（等高线流动等） */
    animate?: boolean
    /** 数据未到位：骨架屏 */
    loading?: boolean
    height?: string
    /** 教学点睛句（契约里的 climaxNote） */
    note?: string
  }>(),
  { title: '', hint: '', legend: () => [], animate: true, loading: false, height: 'clamp(320px, 48vh, 480px)', note: '' },
)

const emit = defineEmits<{ ready: [engine: SceneEngine] }>()

const host = ref<HTMLElement | null>(null)
const engineRef = shallowRef<SceneEngine | null>(null)
const glError = ref('')
const manualPause = ref(false)
const autoRotate = ref(false)
const { active } = useAnimActive(host)

const running = computed(() => active.value && !manualPause.value && props.animate)

function syncPause() {
  const engine = engineRef.value
  if (!engine) return
  engine.setPause('hidden', !active.value)
  engine.setPause('manual', manualPause.value || !props.animate)
  engine.setPause('noData', props.loading)
  engine.autoRotate = autoRotate.value && active.value
}

onMounted(() => {
  if (!host.value) return
  try {
    const engine = new SceneEngine(host.value)
    engine.onError = (msg) => (glError.value = msg)
    engineRef.value = engine
    syncPause()
    emit('ready', engine)
  } catch (err) {
    glError.value = `这个浏览器/显卡起不了 WebGL：${String(err)}`
  }
})

onBeforeUnmount(() => {
  engineRef.value?.dispose()
  engineRef.value = null
})

watch(active, syncPause)
watch(manualPause, syncPause)
watch(autoRotate, syncPause)
watch(() => props.loading, syncPause)
watch(running, (on) => {
  if (on) engineRef.value?.startLoop()
})

function view(kind: 'top' | 'front' | 'side' | 'default') {
  engineRef.value?.setView(kind)
}
function reset() {
  const engine = engineRef.value
  engine?.resetCamera()
  engine?.renderOnce()
}
</script>

<template>
  <section class="scene3d">
    <header v-if="title || hint" class="scene-head">
      <div class="scene-head-text">
        <h4 v-if="title">{{ title }}</h4>
        <p v-if="hint" class="muted tiny">{{ hint }}</p>
      </div>
      <div class="row scene-tools">
        <button class="btn btn-sm" :disabled="!engineRef" @click="manualPause = !manualPause">
          {{ manualPause ? '继续' : '暂停' }}
        </button>
        <button class="btn btn-sm" :class="{ 'btn-primary': autoRotate }" :disabled="!engineRef" @click="autoRotate = !autoRotate">
          自动旋转
        </button>
        <div class="seg" role="group" aria-label="视角">
          <button class="btn btn-sm" :disabled="!engineRef" @click="view('default')">斜视</button>
          <button class="btn btn-sm" :disabled="!engineRef" @click="view('top')">俯视</button>
          <button class="btn btn-sm" :disabled="!engineRef" @click="view('front')">正视</button>
          <button class="btn btn-sm" :disabled="!engineRef" @click="view('side')">侧视</button>
        </div>
        <button class="btn btn-sm" :disabled="!engineRef" @click="reset">重置视角</button>
      </div>
    </header>

    <div class="panel-3d" :style="{ height }">
      <div ref="host" class="scene-host" />

      <div v-if="legend && legend.length" class="scene-legend">
        <div v-for="(l, i) in legend" :key="`${l.label}-${i}`" class="legend-row">
          <span class="sw" :style="{ background: l.color }" />
          <span class="legend-label">{{ l.label }}</span>
        </div>
      </div>

      <div v-if="loading" class="scene-skeleton">
        <div class="skeleton sk-block" />
        <span class="tiny">正在准备 3D 数据…</span>
      </div>

      <div v-else-if="glError" class="scene-error">
        <div class="err-banner">{{ glError }}</div>
      </div>

      <div v-if="!running && !loading" class="scene-paused">{{ manualPause ? '已暂停' : '不在视口内 · 已暂停省电' }}</div>

      <div class="scene-hud">
        <span class="chip hud-chip">拖动旋转 · 滚轮/双指缩放 · 右键平移</span>
      </div>

      <div v-if="note" class="scene-note">
        <div class="note-chip">{{ note }}</div>
      </div>

      <slot name="overlay" />
    </div>

    <slot />
  </section>
</template>

<style scoped>
.scene3d {
  display: block;
}
.scene-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 7px;
}
.scene-head h4 {
  margin: 0;
  font-size: 14.5px;
}
.scene-head-text p {
  margin: 2px 0 0;
  max-width: 74ch;
}
.scene-tools {
  gap: 6px;
}
.seg {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
}
.seg .btn {
  border: none;
  border-radius: 0;
  border-right: 1px solid var(--line-2);
}
.seg .btn:last-child {
  border-right: none;
}
.scene-host {
  position: absolute;
  inset: 0;
}
.scene-skeleton,
.scene-error {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 8px;
  background: rgba(13, 20, 36, 0.55);
  color: #cbd5e1;
  z-index: 5;
}
.sk-block {
  width: 55%;
  height: 46%;
  background: rgba(255, 255, 255, 0.16);
}
.hud-chip {
  background: rgba(255, 255, 255, 0.9);
  border-color: rgba(13, 20, 36, 0.16);
  color: #101a2c;
  font-weight: 500;
}
.note-chip {
  display: inline-block;
  background: rgba(255, 248, 224, 0.95);
  border: 1px solid #f0d696;
  color: #6b4e0d;
  border-radius: 10px;
  padding: 5px 9px;
  font-size: 12.5px;
  line-height: 1.5;
  max-width: 100%;
}
.legend-row {
  display: flex;
  align-items: center;
  gap: 6px;
  line-height: 1.45;
}
.legend-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 720px) {
  .scene-tools {
    flex-wrap: wrap;
  }
}
</style>
