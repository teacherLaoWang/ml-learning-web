<script setup lang="ts">
/** vector3d 面板：箭头条目 + 点（PCA 主成分、梯度场） */
import { computed, onBeforeUnmount, shallowRef, watch } from 'vue'
import Scene3D from './Scene3D.vue'
import { VectorWorld } from '../three/vectorWorld'
import type { SceneEngine } from '../three/engine'
import type { LegendItem, Vector3DVisual } from '../types'
import { labelColor } from '../utils/palette'

const props = withDefaults(
  defineProps<{
    visual: Vector3DVisual
    progress?: number
    loading?: boolean
    height?: string
    /** 页面/面板不可见时关掉内在动画 */
    active?: boolean
  }>(),
  { progress: 1, loading: false, height: 'clamp(320px, 48vh, 480px)', active: true },
)

const engine = shallowRef<SceneEngine | null>(null)
let world: VectorWorld | null = null

function rebuild() {
  world?.dispose()
  world = null
  const e = engine.value
  const data = props.visual?.data
  if (!e || !data?.arrows?.length) return
  world = new VectorWorld(e, data)
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

const legend = computed<LegendItem[]>(() =>
  (props.visual?.data?.arrows ?? [])
    .filter((a) => a.label)
    .slice(0, 8)
    .map((a, i) => ({ label: a.label as string, color: a.color ?? labelColor(i, i) })),
)
</script>

<template>
  <Scene3D
    :title="visual?.title"
    :hint="visual?.hint"
    :legend="legend"
    :loading="loading || !visual?.data?.arrows?.length"
    :height="height"
    :animate="active !== false"
    @ready="onReady"
  />
</template>
