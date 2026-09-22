<script setup lang="ts">
/** surface3d 面板：曲面 mesh + 顶点色高度渐变 + 等高线 + 轨迹动画（播放头由父组件控制） */
import { computed, onBeforeUnmount, shallowRef, watch } from 'vue'
import Scene3D from './Scene3D.vue'
import { SurfaceWorld } from '../three/surfaceWorld'
import type { SceneEngine } from '../three/engine'
import type { LegendItem, Surface3DVisual } from '../types'
import { colormapCss } from '../utils/palette'

const props = withDefaults(
  defineProps<{
    visual: Surface3DVisual
    /** 0..1 播放头（父组件的时间轴驱动，不由本组件计时） */
    progress?: number
    loading?: boolean
    height?: string
    /** 页面/面板不可见时关掉内在动画 */
    active?: boolean
  }>(),
  { progress: 1, loading: false, height: 'clamp(320px, 48vh, 480px)', active: true },
)

const engine = shallowRef<SceneEngine | null>(null)
let world: SurfaceWorld | null = null

function rebuild() {
  world?.dispose()
  world = null
  const e = engine.value
  const data = props.visual?.data
  if (!e || !data?.grid) return
  // 构造期就会读 axes.x/.y/.z，缺范围值会直接抛错、整块面板空白 —— 这里先挡掉并留提示
  const ax = data.axes ?? ({} as typeof data.axes)
  const ok = [ax?.x, ax?.y, ax?.z].every((r) => r && Number.isFinite(r.min) && Number.isFinite(r.max))
  if (!ok) {
    console.warn('[Surface3D] visual 缺少可用的 axes 范围，已跳过渲染：', props.visual?.id)
    return
  }
  world = new SurfaceWorld(e, data, { progress: () => props.progress })
}

function onReady(e: SceneEngine) {
  engine.value = e
  rebuild()
}

watch(() => props.visual?.data, rebuild)
watch(
  () => props.progress,
  () => {
    if (engine.value?.paused) engine.value.renderOnce()
  },
)
onBeforeUnmount(() => {
  world?.dispose()
  world = null
})

const legend = computed<LegendItem[]>(() => {
  const d = props.visual?.data
  if (!d) return []
  const out: LegendItem[] = [
    { label: `${d.axes?.z?.label ?? '值'} 低`, color: colormapCss(0.1) },
    { label: `${d.axes?.z?.label ?? '值'} 高`, color: colormapCss(0.92) },
  ]
  if (d.path?.length) out.push({ label: '下降轨迹', color: '#ffd166' })
  if (d.optimum) out.push({ label: d.optimum.label ?? '最优', color: '#16a34a' })
  if (d.window) out.push({ label: '卷积窗口', color: '#ffd166' })
  return out
})
</script>

<template>
  <Scene3D
    :title="visual?.title"
    :hint="visual?.hint"
    :note="visual?.data?.climaxNote"
    :legend="legend"
    :loading="loading || !visual?.data?.grid"
    :height="height"
    :animate="active !== false"
    @ready="onReady"
  />
</template>
