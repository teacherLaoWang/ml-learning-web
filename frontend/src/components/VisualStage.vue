<script setup lang="ts">
/**
 * visual 面板区：按 kind 分派组件（契约 §2），多个 visual 用页签或栅格。
 * 播放头在这里换算成 progress 传给每个面板；数据没到齐的面板显示提示，不留白。
 */
import { computed, ref, watch } from 'vue'
import type { Component } from 'vue'
import type { Visual, VisualKind, VisualSpec } from '../types'
import Surface3D from './Surface3D.vue'
import Cloud3D from './Cloud3D.vue'
import Vector3D from './Vector3D.vue'
import Chart2D from './Chart2D.vue'
import Graph2D from './Graph2D.vue'
import SkeletonBlock from './SkeletonBlock.vue'
import { useDocumentVisible } from '../composables/useVisibility'

const props = withDefaults(
  defineProps<{
    specs: VisualSpec[]
    visuals: Visual[]
    frame: number
    maxFrame: number
    loading?: boolean
    algoKey?: string
  }>(),
  { loading: false, algoKey: '' },
)

const visible = useDocumentVisible()

const MAP: Record<VisualKind, Component> = {
  surface3d: Surface3D,
  cloud3d: Cloud3D,
  vector3d: Vector3D,
  line2d: Chart2D,
  bars: Chart2D,
  matrix: Chart2D,
  tree2d: Graph2D,
}

interface Entry {
  id: string
  kind: VisualKind
  title: string
  hint: string
  visual: Visual | null
}

const entries = computed<Entry[]>(() => {
  const used = new Set<string>()
  const list: Entry[] = (props.specs ?? []).map((spec) => {
    const byId = props.visuals.find((v) => !used.has(v.id) && v.id === spec.id)
    const byKind = byId ?? props.visuals.find((v) => !used.has(v.id) && v.kind === spec.kind)
    if (byKind) used.add(byKind.id)
    return { id: spec.id, kind: spec.kind, title: spec.title, hint: spec.hint ?? '', visual: byKind ?? null }
  })
  for (const v of props.visuals ?? []) {
    if (used.has(v.id)) continue
    used.add(v.id)
    list.push({ id: v.id, kind: v.kind, title: v.title ?? v.id, hint: v.hint ?? '', visual: v })
  }
  return list
})

const mode = ref<'tabs' | 'grid'>('tabs')
const tab = ref(0)
watch(entries, (list) => {
  if (tab.value >= list.length) tab.value = 0
})
const current = computed<Entry | undefined>(() => entries.value[tab.value])
const shown = computed(() => (mode.value === 'grid' ? entries.value : current.value ? [current.value] : []))
const progress = computed(() => (props.maxFrame > 0 ? Math.min(1, props.frame / props.maxFrame) : 1))
const missing = computed(() => entries.value.filter((e) => !e.visual).map((e) => e.title))
</script>

<template>
  <div class="stage">
    <div class="row stage-bar">
      <div class="tabs" role="tablist">
        <button
          v-for="(e, i) in entries"
          :key="e.id"
          class="tab"
          :class="{ on: mode === 'tabs' && i === tab }"
          role="tab"
          :aria-selected="mode === 'tabs' && i === tab"
          @click="((mode = 'tabs'), (tab = i))"
        >
          {{ e.title }}
          <i v-if="!e.visual" class="miss-dot" />
        </button>
      </div>
      <div class="row right">
        <span class="chip mono tiny">progress {{ (progress * 100).toFixed(0) }}%</span>
        <div class="seg">
          <button class="btn btn-sm" :class="{ 'btn-primary': mode === 'tabs' }" @click="mode = 'tabs'">页签</button>
          <button class="btn btn-sm" :class="{ 'btn-primary': mode === 'grid' }" @click="mode = 'grid'">栅格</button>
        </div>
      </div>
    </div>

    <p v-if="missing.length" class="miss tiny">
      后端还没返回：<b>{{ missing.join('、') }}</b>
      <span v-if="algoKey" class="mono">（app/ml/{{ algoKey }}.py）</span>
    </p>

    <div v-if="loading" class="grid two">
      <div v-for="i in 2" :key="i" class="skeleton" style="height: 320px" />
    </div>

    <div v-else class="panels" :class="mode">
      <div v-for="e in shown" :key="e.id" class="panel">
        <component
          :is="MAP[e.kind]"
          v-if="e.visual"
          :visual="e.visual"
          :progress="progress"
          :active="visible"
        />
        <SkeletonBlock v-else :lines="2" height="300px" :label="`${e.title}：等待 /fit 返回`" />
        <p v-if="!e.visual" class="empty tiny">
          这个 visual 缺数据：切到「离线演示」可以先看动画（fixtures/{{ algoKey || e.id }}.json）。
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stage {
  display: grid;
  gap: 8px;
}
.stage-bar {
  justify-content: space-between;
  gap: 8px;
}
.tabs {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}
.tab {
  position: relative;
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  white-space: nowrap;
  color: var(--ink-2);
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 4px 11px;
  cursor: pointer;
}
.tab.on {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.miss-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--warn);
  margin-left: 5px;
  vertical-align: middle;
}
.right {
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
}
.miss {
  margin: 0;
  color: var(--warn);
}
.grid.two {
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}
.panels.grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(430px, 1fr));
}
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 11px 12px 12px;
  box-shadow: var(--shadow);
}
.empty {
  color: var(--muted);
  margin: 6px 0 0;
}
@media (max-width: 560px) {
  .panels.grid {
    grid-template-columns: 1fr;
  }
}
</style>
