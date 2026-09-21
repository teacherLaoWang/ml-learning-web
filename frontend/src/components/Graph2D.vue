<script setup lang="ts">
/**
 * tree2d 面板：决策树结构与神经网络结构图共用。
 * 节点内的文字一律带白色描边（paint-order: stroke），保证压在圆/矩形上仍可读。
 * 边按深度随播放头逐层揭开，并用流动虚线表示信号方向。
 */
import { computed, ref } from 'vue'
import type { Tree2DData, Tree2DVisual, TreeNode } from '../types'
import { clamp } from '../utils/format'
import { PALETTE } from '../utils/palette'

const props = withDefaults(
  defineProps<{
    visual: Tree2DVisual
    progress?: number
    loading?: boolean
    active?: boolean
  }>(),
  { progress: 1, loading: false, active: true },
)

const W = 680
const H = 340
const PAD = 46

const data = computed<Tree2DData>(() => props.visual?.data ?? { nodes: [], edges: [] })

const model = computed(() => {
  const nodes = data.value.nodes ?? []
  const xs = nodes.map((n) => n.x)
  const ys = nodes.map((n) => n.y)
  const xmin = Math.min(...xs, 0)
  const xmax = Math.max(...xs, 1)
  const ymin = Math.min(...ys, 0)
  const ymax = Math.max(...ys, 1)
  const toPx = (n: TreeNode) => ({
    x: PAD + ((n.x - xmin) / (xmax - xmin || 1)) * (W - 2 * PAD),
    y: PAD + ((n.y - ymin) / (ymax - ymin || 1)) * (H - 2 * PAD - 20),
  })
  const placed = nodes.map((n) => {
    const p = toPx(n)
    const w = Math.max(46, estWidth(n.title, 11.5) + 16)
    const h = n.value !== undefined ? 26 : 20 + (n.lines?.length ?? 0) * 12
    return { node: n, x: p.x, y: p.y, w, h, depth: n.y }
  })
  const byId = new Map(placed.map((p) => [p.node.id, p]))
  const maxDepth = ymax - ymin || 1
  const edges = (data.value.edges ?? [])
    .map((e) => {
      const a = byId.get(e.from)
      const b = byId.get(e.to)
      if (!a || !b) return null
      const ay = a.y + a.h / 2
      const by = b.y - b.h / 2
      const mid = (ay + by) / 2
      const d = `M ${a.x} ${ay} C ${a.x} ${mid}, ${b.x} ${mid}, ${b.x} ${by}`
      return {
        d,
        label: e.label,
        weight: e.weight,
        lx: (a.x + b.x) / 2,
        ly: mid,
        depth: b.depth,
        from: e.from,
        to: e.to,
      }
    })
    .filter((e): e is NonNullable<typeof e> => !!e)
  return { placed, byId, edges, maxDepth, nodeCount: placed.length, edgeCount: edges.length }
})

/** 用「播放头」按层揭开：树越深、网络越宽，越能看清信号怎么走 */
function reveal(depth: number): number {
  const max = model.value.maxDepth
  const t = clamp(props.progress, 0.02, 1) * (max + 0.6)
  return clamp((t - depth) / 0.7, 0, 1)
}

const hover = ref<{ x: number; y: number; title: string; lines: string[] } | null>(null)
const focusId = ref<number | null>(null)

const highlighted = computed(() => {
  if (focusId.value === null) return null
  const set = new Set<number>([focusId.value])
  let grew = true
  while (grew) {
    grew = false
    for (const e of model.value.edges) {
      if (set.has(e.from) && !set.has(e.to)) {
        set.add(e.to)
        grew = true
      }
      if (set.has(e.to) && !set.has(e.from)) {
        set.add(e.from)
        grew = true
      }
    }
  }
  return set
})

/* 拖拽平移 + 滚轮缩放：结构图大了要能局部看 */
const view = ref({ k: 1, tx: 0, ty: 0 })
let dragging: { x: number; y: number; tx: number; ty: number } | null = null

function onWheel(ev: WheelEvent) {
  ev.preventDefault()
  const k = clamp(view.value.k * (ev.deltaY > 0 ? 0.9 : 1.1), 0.6, 4)
  view.value = { ...view.value, k }
}
function onDown(ev: PointerEvent) {
  dragging = { x: ev.clientX, y: ev.clientY, tx: view.value.tx, ty: view.value.ty }
  ;(ev.currentTarget as Element).setPointerCapture?.(ev.pointerId)
}
function onMove(ev: PointerEvent) {
  if (!dragging) return
  view.value = {
    ...view.value,
    tx: dragging.tx + (ev.clientX - dragging.x) * 0.9,
    ty: dragging.ty + (ev.clientY - dragging.y) * 0.9,
  }
}
function onUp() {
  dragging = null
}
function resetView() {
  view.value = { k: 1, tx: 0, ty: 0 }
}

interface PlacedNode {
  node: TreeNode
  x: number
  y: number
  w: number
  h: number
  depth: number
}

function enterNode(p: PlacedNode) {
  focusId.value = p.node.id
  hover.value = { x: p.x, y: p.y - p.h / 2, title: p.node.title, lines: p.node.lines ?? [] }
}
function leaveNode() {
  focusId.value = null
  hover.value = null
}

function nodeFill(n: TreeNode, i: number): string {
  return n.color ?? (n.leaf ? '#0d9488' : PALETTE[i % PALETTE.length])
}

function estWidth(s: string, fs: number): number {
  let w = 0
  for (const ch of s) w += /[一-龥　-〿＀-￯]/.test(ch) ? fs : fs * 0.56
  return w
}

const stats = computed(() => `${model.value.nodeCount} 个节点 · ${model.value.edgeCount} 条边`)
</script>

<template>
  <div class="graph2d" :class="{ paused: !active }">
    <div class="card-head">
      <div>
        <h4>{{ visual?.title }}</h4>
        <p v-if="visual?.hint" class="muted tiny">{{ visual.hint }}</p>
      </div>
      <div class="row">
        <span class="chip tiny">{{ stats }}</span>
        <button class="btn btn-sm" @click="resetView">复位</button>
      </div>
    </div>

    <div v-if="loading" class="skeleton" style="height: 260px" />
    <svg
      v-else
      class="chart-svg graph-svg"
      :viewBox="`0 0 ${W} ${H}`"
      @wheel="onWheel"
      @pointerdown="onDown"
      @pointermove="onMove"
      @pointerup="onUp"
      @pointercancel="onUp"
    >
      <g :transform="`translate(${view.tx} ${view.ty}) scale(${view.k}) translate(${(1 - view.k) * W / 2} ${(1 - view.k) * H / 2})`">
        <g v-for="(e, i) in model.edges" :key="`e${i}`" :opacity="reveal(e.depth)">
          <path class="edge" :d="e.d" :class="{ flow: active }" :stroke-width="clamp(Math.abs(e.weight ?? 1) * 2.2, 1.2, 4)" />
          <text v-if="e.label" class="edge-label" :x="e.lx + 4" :y="e.ly">{{ e.label }}</text>
          <text v-else-if="e.weight !== undefined" class="edge-weight" :x="e.lx + 4" :y="e.ly">w={{ e.weight.toFixed(2) }}</text>
        </g>

        <g
          v-for="(p, i) in model.placed"
          :key="`n${p.node.id}`"
          class="node-g"
          :opacity="reveal(p.depth)"
          :class="{ dim: highlighted && !highlighted.has(p.node.id) }"
          @pointerenter="enterNode(p)"
          @pointerleave="leaveNode()"
        >
          <!-- 圆形神经元：文字带白色描边，与圆底分开 -->
          <template v-if="p.node.value !== undefined">
            <circle :cx="p.x" :cy="p.y" :r="14" :fill="nodeFill(p.node, i)" :opacity="0.25 + 0.7 * clamp(p.node.value, 0, 1)" />
            <circle class="ring" :cx="p.x" :cy="p.y" r="14" :stroke="nodeFill(p.node, i)" />
            <text class="node-title in-circle" :x="p.x" :y="p.y + 4" text-anchor="middle">{{ p.node.title }}</text>
          </template>
          <template v-else>
            <rect
              class="node-box"
              :x="p.x - p.w / 2"
              :y="p.y - p.h / 2"
              :width="p.w"
              :height="p.h"
              :class="{ leaf: p.node.leaf }"
              :stroke="nodeFill(p.node, i)"
              rx="7"
            />
            <text class="node-title" :x="p.x" :y="p.y - p.h / 2 + 14" text-anchor="middle">{{ p.node.title }}</text>
            <text
              v-for="(line, li) in p.node.lines ?? []"
              :key="`l${li}`"
              class="node-line"
              :x="p.x"
              :y="p.y - p.h / 2 + 27 + li * 12"
              text-anchor="middle"
            >
              {{ line }}
            </text>
          </template>
        </g>
      </g>
    </svg>

    <div v-if="hover" class="graph-tip" :style="{ left: `${(hover.x / W) * 100}%`, top: `${(hover.y / H) * 100}%` }">
      <b>{{ hover.title }}</b>
      <div v-for="(l, i) in hover.lines" :key="i" class="tiny">{{ l }}</div>
    </div>
    <p class="muted tiny drag-hint">拖动平移 · 滚轮缩放 · 悬停高亮一条路径</p>
  </div>
</template>

<style scoped>
.graph2d {
  position: relative;
  padding: 10px 12px 6px;
}
.graph2d h4 {
  margin: 0;
  font-size: 14px;
}
.graph-svg {
  touch-action: none;
  cursor: grab;
  background: linear-gradient(180deg, #fbfcff, #f4f7fd);
  border: 1px solid var(--line-2);
  border-radius: 10px;
}
.edge {
  fill: none;
  stroke: #93a4c3;
  stroke-dasharray: 7 5;
  transition: opacity 0.18s linear;
}
.edge-label {
  font-size: 10.5px;
  font-weight: 700;
  fill: #1d4ed8;
}
.edge-weight {
  font-size: 9.5px;
  fill: #64748b;
  font-family: var(--mono);
}
.node-box {
  fill: #fff;
  stroke-width: 1.6;
}
.node-box.leaf {
  fill: #ecfdf6;
}
.ring {
  fill: none;
  stroke-width: 1.8;
}
.node-title {
  font-size: 11.5px;
  font-weight: 700;
  fill: var(--ink);
  paint-order: stroke;
  stroke: #fff;
  stroke-width: 3.2px;
  stroke-linejoin: round;
  pointer-events: none;
}
.node-title.in-circle {
  fill: #0b1220;
  font-size: 10.5px;
}
.node-line {
  font-size: 10px;
  fill: var(--ink-2);
  paint-order: stroke;
  stroke: #fff;
  stroke-width: 2.6px;
  pointer-events: none;
}
.node-g {
  cursor: pointer;
  transition: opacity 0.2s linear;
}
.node-g.dim {
  opacity: 0.32;
}
.graph-tip {
  position: absolute;
  transform: translate(-50%, -110%);
  background: rgba(16, 26, 44, 0.94);
  color: #e2e8f0;
  border-radius: 8px;
  padding: 5px 8px;
  font-size: 11.5px;
  pointer-events: none;
  white-space: nowrap;
  z-index: 4;
}
.drag-hint {
  margin: 4px 0 0;
  text-align: right;
}
.paused .edge {
  animation-play-state: paused;
}
</style>
