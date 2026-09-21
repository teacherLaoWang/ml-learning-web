<script setup lang="ts">
/** cloud3d 面板：散点按 label 着色 + 可选分割面/投影面；点云旋转时靠遮挡关系看清前后 */
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import Scene3D from './Scene3D.vue'
import { CloudWorld } from '../three/cloudWorld'
import type { SceneEngine } from '../three/engine'
import type { Cloud3DVisual, LegendItem } from '../types'

const props = withDefaults(
  defineProps<{
    visual: Cloud3DVisual
    progress?: number
    loading?: boolean
    height?: string
    /** 页面/面板不可见时关掉内在动画 */
    active?: boolean
  }>(),
  { progress: 1, loading: false, height: 'clamp(320px, 48vh, 480px)', active: true },
)

const engine = shallowRef<SceneEngine | null>(null)
const worldLegend = ref<LegendItem[]>([])
let world: CloudWorld | null = null

function rebuild() {
  world?.dispose()
  world = null
  const e = engine.value
  const data = props.visual?.data
  if (!e || !data?.points?.length) {
    worldLegend.value = []
    return
  }
  world = new CloudWorld(e, data, { progress: () => props.progress })
  worldLegend.value = world.getLegend().slice(0, 8)
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
  if (worldLegend.value.length) return worldLegend.value
  return (props.visual?.data?.legend ?? []).slice(0, 8).map((l) => ({ label: String(l.label), color: l.color }))
})
</script>

<template>
  <Scene3D
    :title="visual?.title"
    :hint="visual?.hint"
    :legend="legend"
    :loading="loading || !visual?.data?.points?.length"
    :height="height"
    :animate="active !== false"
    @ready="onReady"
  />
</template>
