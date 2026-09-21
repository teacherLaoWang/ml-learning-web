<script setup lang="ts">
/**
 * 通用 2D SVG 图：line2d / bars / matrix 三种（契约 §2）。
 * 坐标轴带刻度、hover 读数；动画由 progress（父组件播放头）驱动，
 * 页面不可见时 CSS 流动动画一并暂停（body.is-hidden + paused class）。
 */
import { computed, ref } from 'vue'
import type { BarsData, Line2DData, MatrixData, Visual } from '../types'
import { clamp, fmtNum, fmtTick, niceTicks } from '../utils/format'
import { colormapCss, PALETTE } from '../utils/palette'

const props = withDefaults(
  defineProps<{
    visual: Extract<Visual, { kind: 'line2d' | 'bars' | 'matrix' }>
    progress?: number
    loading?: boolean
    active?: boolean
  }>(),
  { progress: 1, loading: false, active: true },
)

const W = 660
const H = 320
const PAD = { l: 62, r: 16, t: 16, b: 38 }
const PLOT_W = W - PAD.l - PAD.r
const PLOT_H = H - PAD.t - PAD.b

const kind = computed(() => props.visual.kind)
const title = computed(() => props.visual.title ?? '')
const hint = computed(() => props.visual.hint ?? '')

const hover = ref<{ x: number; y: number; lines: string[] } | null>(null)

/* ---------------------------------------------------------------- line2d */

interface PtModel {
  x: number
  y: number
  px: number
  py: number
}
interface CurveModel {
  id: string
  label: string
  color: string
  dash: boolean
  pts: PtModel[]
}

const lineModel = computed(() => {
  if (kind.value !== 'line2d' || !props.visual?.data) return null
  const data = props.visual.data as Line2DData
  const curves = (data.curves ?? []).filter((c) => Array.isArray(c.x) && Array.isArray(c.y) && c.x.length >= 2)
  const xs = curves.flatMap((c) => c.x)
  const ys = curves.flatMap((c) => c.y)
  const xr = data.axes?.x
  const yr = data.axes?.y
  const xmin = xr?.min ?? Math.min(...xs, 0)
  const xmax = xr?.max ?? Math.max(...xs, 1)
  const ymin = yr?.min ?? Math.min(...ys, 0)
  const ymax = yr?.max ?? Math.max(...ys, 1)
  const spanX = xmax - xmin || 1
  const spanY = ymax - ymin || 1
  const xToPx = (x: number) => PAD.l + ((x - xmin) / spanX) * PLOT_W
  const yToPx = (y: number) => PAD.t + PLOT_H - ((y - ymin) / spanY) * PLOT_H
  const models: CurveModel[] = curves.map((c, i) => ({
    id: c.id || `c${i}`,
    label: c.label || c.id || `曲线 ${i + 1}`,
    color: c.color ?? PALETTE[i % PALETTE.length],
    dash: !!c.dash,
    pts: c.x.map((x, k) => ({ x, y: c.y[k] ?? 0, px: xToPx(x), py: yToPx(c.y[k] ?? 0) })),
  }))
  return {
    curves: models,
    xLabel: xr?.label ?? 'x',
    yLabel: yr?.label ?? 'y',
    xTicks: niceTicks(xmin, xmax, 5),
    yTicks: niceTicks(ymin, ymax, 5),
    diagonal: !!data.diagonal,
    diagPath:
      data.diagonal && xmax - xmin > 0 && ymax - ymin > 0
        ? `M ${xToPx(xmin)} ${yToPx(ymin)} L ${xToPx(xmax)} ${yToPx(ymax)}`
        : '',
    xmin,
    xmax,
    xToPx,
    yToPx,
  }
})

/** 播放头：只画到 progress 处，于是学习曲线是真的「长」出来的 */
function linePath(c: CurveModel, progress: number): string {
  const n = c.pts.length
  const keep = Math.max(2, Math.ceil(n * clamp(progress, 0.02, 1)))
  return c.pts
    .slice(0, keep)
    .map((p, i) => `${i ? 'L' : 'M'} ${p.px.toFixed(1)} ${p.py.toFixed(1)}`)
    .join(' ')
}

const lineHead = computed(() => {
  const m = lineModel.value
  if (!m?.curves.length) return null
  const first = m.curves[0]
  const keep = Math.max(2, Math.ceil(first.pts.length * clamp(props.progress, 0.02, 1)))
  return first.pts[keep - 1] ?? first.pts[first.pts.length - 1]
})

function onLineMove(ev: MouseEvent) {
  const m = lineModel.value
  if (!m) return
  const rect = (ev.currentTarget as SVGRectElement).getBoundingClientRect()
  const px = ((ev.clientX - rect.left) / rect.width) * W
  const frac = clamp((px - PAD.l) / PLOT_W, 0, 1)
  const n = m.curves[0]?.pts.length ?? 0
  if (!n) return
  const idx = Math.min(n - 1, Math.round(frac * (n - 1)))
  const lines = m.curves.map((c) => `${c.label}: ${fmtNum(c.pts[idx]?.y, 4)}`)
  const anchor = m.curves[0].pts[idx]
  hover.value = { x: anchor.px, y: PAD.t, lines: [`x=${fmtNum(anchor.x, 4)}`, ...lines] }
}

/* ------------------------------------------------------------------- bars */

const barModel = computed(() => {
  if (kind.value !== 'bars' || !props.visual?.data) return null
  const data = props.visual.data as BarsData
  const labels = data.labels ?? []
  const values = data.values ?? []
  const vmax = Math.max(...values, 0, data.axes?.y?.max ?? 0)
  const vmin = Math.min(...values, 0, data.axes?.y?.min ?? 0)
  const span = vmax - vmin || 1
  const n = Math.max(1, labels.length)
  const slot = PLOT_W / n
  const bw = Math.max(6, Math.min(58, slot * 0.66))
  const y0 = PAD.t + PLOT_H - ((0 - vmin) / span) * PLOT_H
  const bars = labels.map((label, i) => {
    const v = values[i] ?? 0
    const py = PAD.t + PLOT_H - ((v - vmin) / span) * PLOT_H
    return {
      label: String(label),
      value: v,
      x: PAD.l + slot * i + (slot - bw) / 2,
      w: bw,
      y: Math.min(py, y0),
      h: Math.max(1.5, Math.abs(y0 - py)),
      top: py,
      color: PALETTE[i % PALETTE.length],
    }
  })
  return {
    bars,
    yTicks: niceTicks(vmin, vmax, 5),
    yLabel: data.axes?.y?.label ?? '值',
    unit: data.unit ?? '',
    y0,
    yToPx: (v: number) => PAD.t + PLOT_H - ((v - vmin) / span) * PLOT_H,
    vmin,
    vmax,
  }
})

/* ----------------------------------------------------------------- matrix */

const matrixModel = computed(() => {
  if (kind.value !== 'matrix' || !props.visual?.data) return null
  const data = props.visual.data as MatrixData
  const labels = (data.labels ?? []).map(String)
  const rows = data.rows ?? []
  const n = Math.max(labels.length, rows.length)
  const grid: number[][] = rows.map((r) => r.map((v) => Number(v) || 0))
  let diverging = false
  let lo = Infinity
  let hi = -Infinity
  for (const row of grid) for (const v of row) {
    if (v < 0) diverging = true
    lo = Math.min(lo, v)
    hi = Math.max(hi, v)
  }
  if (!Number.isFinite(lo)) {
    lo = 0
    hi = 1
  }
  const cells: Array<{ r: number; c: number; v: number; shown: string; fill: string }> = []
  for (let r = 0; r < n; r++) {
    const row = grid[r] ?? []
    const total = row.reduce((a, b) => a + b, 0) || 1
    for (let c = 0; c < n; c++) {
      const v = row[c] ?? 0
      const shown = data.percent ? `${((v / total) * 100).toFixed(1)}%` : fmtNum(v, 3)
      const t = diverging ? v / Math.max(Math.abs(lo), Math.abs(hi) || 1) : (v - lo) / ((hi - lo) || 1)
      cells.push({ r, c, v, shown, fill: cellFill(t, diverging) })
    }
  }
  const size = Math.min(PLOT_W, PLOT_H + PAD.t)
  const cell = size / Math.max(1, n)
  const ox = PAD.l + (PLOT_W - size) / 2
  const oy = PAD.t + 6
  return { labels, cells, cell, ox, oy, size, diverging, title: data.title ?? '' }
})

function cellFill(t: number, diverging: boolean): string {
  if (diverging) return colormapCss(clamp(t, -1, 1), 'diverge', 0.92)
  return colormapCss(clamp(t, 0, 1), 'viridis', 0.92)
}

function textOn(rgb: string): string {
  const m = rgb.match(/(\d+(\.\d+)?)/g)
  if (!m) return '#101a2c'
  const [r, g, b] = m.map(Number)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 ? '#101a2c' : '#f8fafc'
}

function onMatrixMove(r: number, c: number, v: number, shown: string) {
  const model = matrixModel.value
  if (!model) return
  const px = model.ox + (c + 0.5) * model.cell
  const py = model.oy + (r + 0.5) * model.cell
  hover.value = {
    x: px,
    y: py,
    lines: [`${model.labels[r] ?? r} × ${model.labels[c] ?? c}`, `值 ${v}`, ...((props.visual.data as MatrixData).percent ? [`行内占比 ${shown}`] : [])],
  }
}

const tooltipStyle = computed(() => {
  const h = hover.value
  if (!h) return {}
  const leftPct = (h.x / W) * 100
  return {
    left: `${clamp(leftPct, 4, 74)}%`,
    top: `${clamp((h.y / H) * 100, 4, 70)}%`,
  }
})

</script>

<template>
  <div class="chart2d" :class="{ paused: !active }">
    <div class="card-head">
      <div>
        <h4>{{ title }}</h4>
        <p v-if="hint" class="muted tiny">{{ hint }}</p>
      </div>
      <span v-if="loading" class="chip">计算中…</span>
    </div>

    <div v-if="loading" class="chart-skeleton">
      <div class="skeleton" style="height: 220px" />
    </div>

    <svg v-else class="chart-svg" :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="title">
      <!-- =============================== line2d -->
      <template v-if="lineModel">
        <g v-for="(t, i) in lineModel.yTicks" :key="`gy${i}`">
          <line class="grid-line" :x1="PAD.l" :x2="W - PAD.r" :y1="lineModel.yToPx(t)" :y2="lineModel.yToPx(t)" />
          <text :x="PAD.l - 7" :y="lineModel.yToPx(t) + 4" text-anchor="end">{{ fmtTick(t) }}</text>
        </g>
        <g v-for="(t, i) in lineModel.xTicks" :key="`gx${i}`">
          <line class="grid-line" :y1="PAD.t" :y2="PAD.t + PLOT_H" :x1="lineModel.xToPx(t)" :x2="lineModel.xToPx(t)" />
          <text :x="lineModel.xToPx(t)" :y="H - PAD.b + 16" text-anchor="middle">{{ fmtTick(t) }}</text>
        </g>
        <line class="axis-line" :x1="PAD.l" :x2="W - PAD.r" :y1="PAD.t + PLOT_H" :y2="PAD.t + PLOT_H" />
        <line class="axis-line" :x1="PAD.l" :x2="PAD.l" :y1="PAD.t" :y2="PAD.t + PLOT_H" />
        <path v-if="lineModel.diagPath" :d="lineModel.diagPath" stroke="#cbd5e1" stroke-width="1.4" stroke-dasharray="5 5" fill="none" />

        <path
          v-for="c in lineModel.curves"
          :key="c.id"
          class="curve"
          :stroke="c.color"
          :stroke-dasharray="c.dash ? '6 5' : undefined"
          :d="linePath(c, progress)"
        />
        <circle v-if="lineHead" :cx="lineHead.px" :cy="lineHead.py" r="4.6" :fill="lineModel.curves[0]?.color" stroke="#fff" stroke-width="1.6" />
        <line v-if="lineHead" class="hover-line" :x1="lineHead.px" :x2="lineHead.px" :y1="PAD.t" :y2="PAD.t + PLOT_H" />

        <text :x="PAD.l + PLOT_W / 2" :y="H - 4" text-anchor="middle" class="axis-name">{{ lineModel.xLabel }}</text>
        <text :x="14" :y="PAD.t + PLOT_H / 2" text-anchor="middle" class="axis-name" :transform="`rotate(-90 14 ${PAD.t + PLOT_H / 2})`">
          {{ lineModel.yLabel }}
        </text>

        <g class="legend">
          <template v-for="(c, i) in lineModel.curves" :key="`lg${c.id}`">
            <rect :x="PAD.l + i * 132" :y="6" width="10" height="4" rx="2" :fill="c.color" />
            <text :x="PAD.l + i * 132 + 14" :y="11">{{ c.label }}</text>
          </template>
        </g>

        <rect
          :x="PAD.l"
          :y="PAD.t"
          :width="PLOT_W"
          :height="PLOT_H"
          fill="transparent"
          @mousemove="onLineMove"
          @mouseleave="hover = null"
        />
      </template>

      <!-- ================================== bars -->
      <template v-else-if="barModel">
        <g v-for="(t, i) in barModel.yTicks" :key="`by${i}`">
          <line class="grid-line" :x1="PAD.l" :x2="W - PAD.r" :y1="barModel.yToPx(t)" :y2="barModel.yToPx(t)" />
          <text :x="PAD.l - 7" :y="barModel.yToPx(t) + 4" text-anchor="end">{{ fmtTick(t) }}</text>
        </g>
        <line class="axis-line" :x1="PAD.l" :x2="W - PAD.r" :y1="barModel.y0" :y2="barModel.y0" />
        <g v-for="(b, i) in barModel.bars" :key="`bar${i}`" class="bar-g">
          <rect
            class="bar"
            :x="b.x"
            :width="b.w"
            :y="b.y + b.h * (1 - clamp((progress * barModel.bars.length - i) / 1, 0, 1))"
            :height="b.h * clamp((progress * barModel.bars.length - i) / 1, 0, 1)"
            :fill="b.color"
            rx="3"
            @mousemove="hover = { x: b.x + b.w / 2, y: b.y - 6, lines: [b.label, `${fmtNum(b.value, 4)}${barModel.unit}`] }"
            @mouseleave="hover = null"
          />
          <text :x="b.x + b.w / 2" :y="b.y - 5" text-anchor="middle" class="bar-value">
            {{ clamp(progress * barModel.bars.length - i, 0, 1) > 0.5 ? fmtNum(b.value, 3) : '' }}
          </text>
          <text :x="b.x + b.w / 2" :y="H - PAD.b + 15" text-anchor="middle" class="bar-label">{{ b.label }}</text>
        </g>
        <text :x="14" :y="PAD.t + PLOT_H / 2" text-anchor="middle" class="axis-name" :transform="`rotate(-90 14 ${PAD.t + PLOT_H / 2})`">
          {{ barModel.yLabel }}
        </text>
      </template>

      <!-- ================================ matrix -->
      <template v-else-if="matrixModel">
        <text :x="W / 2" :y="13" text-anchor="middle" class="axis-name">{{ matrixModel.title }}</text>
        <g v-for="(l, i) in matrixModel.labels" :key="`mx${i}`">
          <text :x="matrixModel.ox - 8" :y="matrixModel.oy + (i + 0.62) * matrixModel.cell" text-anchor="end">{{ l }}</text>
          <text :x="matrixModel.ox + (i + 0.5) * matrixModel.cell" :y="matrixModel.oy + matrixModel.size + 15" text-anchor="middle">
            {{ l }}
          </text>
        </g>
        <g v-for="(cell, i) in matrixModel.cells" :key="`mc${i}`">
          <rect
            class="mcell"
            :x="matrixModel.ox + cell.c * matrixModel.cell + 1.5"
            :y="matrixModel.oy + cell.r * matrixModel.cell + 1.5"
            :width="matrixModel.cell - 3"
            :height="matrixModel.cell - 3"
            :fill="cell.fill"
            :opacity="clamp((progress * matrixModel.cells.length - i) / 3, 0.12, 1)"
            rx="4"
            @mousemove="onMatrixMove(cell.r, cell.c, cell.v, cell.shown)"
            @mouseleave="hover = null"
          />
          <text
            v-if="matrixModel.cell > 26"
            class="mcell-text"
            :x="matrixModel.ox + (cell.c + 0.5) * matrixModel.cell"
            :y="matrixModel.oy + (cell.r + 0.62) * matrixModel.cell"
            text-anchor="middle"
            :fill="textOn(cell.fill)"
            :opacity="clamp((progress * matrixModel.cells.length - i) / 3, 0.12, 1)"
          >
            {{ cell.shown }}
          </text>
        </g>
        <text :x="W / 2" :y="H - 6" text-anchor="middle" class="axis-name">预测 →</text>
        <text :x="14" :y="PAD.t + PLOT_H / 2" text-anchor="middle" class="axis-name" :transform="`rotate(-90 14 ${PAD.t + PLOT_H / 2})`">
          真实
        </text>
      </template>
    </svg>

    <div v-if="hover" class="chart-tip" :style="tooltipStyle">
      <div v-for="(l, i) in hover.lines" :key="i">{{ l }}</div>
    </div>
  </div>
</template>

<style scoped>
.chart2d {
  position: relative;
  padding: 10px 12px 12px;
}
.chart2d h4 {
  margin: 0;
  font-size: 14px;
}
.chart-svg {
  margin-top: 4px;
}
.axis-name {
  font-weight: 700;
  fill: var(--ink);
}
.bar,
.mcell {
  transition: opacity 0.16s linear;
}
.bar-g:hover .bar {
  filter: brightness(1.12);
}
.bar-value {
  font-size: 10.5px;
  fill: var(--ink-2);
  font-family: var(--mono);
}
.bar-label {
  font-size: 10.5px;
}
.mcell-text {
  font-size: 11px;
  font-family: var(--mono);
}
.chart-tip {
  position: absolute;
  transform: translate(-50%, -108%);
  background: rgba(16, 26, 44, 0.94);
  color: #f1f5f9;
  border-radius: 8px;
  padding: 5px 8px;
  font-size: 11.5px;
  line-height: 1.5;
  pointer-events: none;
  white-space: nowrap;
  font-family: var(--mono);
  z-index: 4;
}
.legend text {
  font-size: 11px;
}
.chart-skeleton {
  padding: 8px 0;
}
.paused :deep(.flow) {
  animation-play-state: paused;
}
</style>
