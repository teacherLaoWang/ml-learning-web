/**
 * 数据契约的 TypeScript 镜像 —— 唯一事实来源是 `docs/API-CONTRACT.md`。
 * 改动契约时三处同步：`app/content/registry.py`、`app/ml/*`、本文件。
 *
 * 约定（§0）：三维右手系、NumPy 数组已 tolist()、浮点在服务端 round 到 6 位。
 * 坐标归一化与可视尺度全部由前端负责（见 src/three/frame.ts）。
 */

/* ------------------------------------------------------------------ 公共小块 */

/** 一轴的显示范围 + 标签（后端 `util.ax()`） */
export interface AxisRange {
  label: string
  min: number
  max: number
}

export interface Axes3 {
  x: AxisRange
  y: AxisRange
  z: AxisRange
}

/** 规则网格：`z` 形状固定为 `[len(y)][len(x)]`（§2 surface3d 注） */
export interface GridData {
  x: number[]
  y: number[]
  z: number[][]
}

export type Num3 = [number, number, number]

/* ------------------------------------------------------------------ surface3d */

/** 轨迹主角：`step` 是它属于第几步，`grad` 是该点损失对 (x,y) 两个参数的梯度 */
export interface PathPoint {
  x: number
  y: number
  z: number
  step: number
  grad?: number[]
}

export interface SurfaceMarker {
  x: number
  y: number
  z: number
  label?: string
  color?: string
}

/**
 * 可选扩展（契约 §2 未列，但 cnn 的 `app/ml/util.py: surface(window=...)` 已在发这个字段）：
 * 卷积滑动框。真实负载形如
 *   `"window": {"size": 3, "stride": 1, "x": 0, "y": 0, "label": "3×3 卷积核（步长 1，填充 1）"}`
 * 其中 x/y 是窗口左上角在 grid 上的起点（格索引）；前端从该起点按播放头逐格扫过整张图。
 * 不给也能跑：退化为从左上角开始绕圈扫描。
 */
export interface SurfaceWindow {
  /** 窗口边长（格）；也接受 [宽, 高] */
  size?: number | [number, number]
  /** 步长（格） */
  stride?: number
  /** 起点（格索引） */
  x?: number
  y?: number
  /** 每一帧滑动几格（默认 1） */
  cellsPerFrame?: number
  /** 'both' = 先行后列 */
  axis?: 'both' | 'x' | 'y'
  /** 面板图例文字 */
  label?: string
}

export interface Surface3DData {
  axes: Axes3
  grid: GridData
  /** 等高线高度集合 */
  levels?: number[]
  path?: PathPoint[]
  optimum?: SurfaceMarker
  markers?: SurfaceMarker[]
  /** 教学点睛句：面板内以文字条显示 */
  climaxNote?: string
  window?: SurfaceWindow | null
}

/* ------------------------------------------------------------------ cloud3d */

export interface LegendItem {
  label: string | number
  color: string
}

export interface CloudPoint {
  x: number
  y: number
  z: number
  /** 类别：后端可能是 int 也可能是 str（util.point3） */
  label?: number | string
  size?: number
  /** 可选：真实标签（与着色 label 不同时用于 ARI 说明） */
  truth?: number | string
}

/** 分割面：与 surface3d 同构的网格曲面（决策函数 / 概率面） */
export interface CloudBoundary {
  axes: Axes3
  grid: GridData
  /** 为真时额外画出 z=0（或 z=0.5）的等值线 */
  contour0?: boolean
  /** contour0 取值的位置，默认 0 */
  level?: number
}

export interface CloudProjection {
  origin: Num3
  normal: Num3
  label?: string
}

export interface CloudHull {
  label?: number | string
  color?: string
  points: Num3[]
  /** loop = 首尾相连的轮廓（默认）；path = 有序轨迹，不闭合，末端是收敛点 */
  mode?: 'loop' | 'path'
}

/** 可选扩展：质心（kmeans/tree/svm 用），给了就能演示「点被吸入最近中心」 */
export interface CloudCentroid {
  x: number
  y: number
  z: number
  label?: number | string
  size?: number
  step?: number
}

export interface Cloud3DData {
  legend?: LegendItem[]
  points: CloudPoint[]
  boundary?: CloudBoundary | null
  projection?: CloudProjection | null
  hulls?: CloudHull[]
  centroids?: CloudCentroid[]
  /** 收缩动画强度 0..1，默认 0.85 */
  collapse?: number
}

/* ------------------------------------------------------------------ vector3d */

export interface VectorArrow {
  from: Num3
  to: Num3
  color?: string
  label?: string
  dash?: boolean
  /** 箭头粗细（相对 1） */
  width?: number
}

export interface Vector3DData {
  arrows: VectorArrow[]
  points?: CloudPoint[]
  axes?: { x?: string; y?: string; z?: string }
}

/* ------------------------------------------------------------------ line2d */

export interface Curve {
  id: string
  label: string
  x: number[]
  y: number[]
  dash?: boolean
  color?: string
}

export interface Line2DData {
  curves: Curve[]
  axes?: { x?: AxisRange; y?: AxisRange }
  /** 画 y=x 参考线（ROC 用） */
  diagonal?: boolean
}

/* ------------------------------------------------------------------ bars */

export interface BarsData {
  labels: Array<string | number>
  values: number[]
  unit?: string
  axes?: { x?: AxisRange; y?: AxisRange }
}

/* ------------------------------------------------------------------ matrix */

export interface MatrixData {
  labels: Array<string | number>
  rows: number[][]
  title?: string
  /** 为真时按行归一化显示百分比 */
  percent?: boolean
}

/* ------------------------------------------------------------------ tree2d */

export interface TreeNode {
  id: number
  x: number
  y: number
  title: string
  lines?: string[]
  leaf?: boolean
  color?: string
  /** 可选扩展：节点强度 0..1（网络结构图用它做激活热力） */
  value?: number
}

export interface TreeEdge {
  from: number
  to: number
  label?: string
  /** 可选扩展：边权重，用于粗细/流动速度 */
  weight?: number
}

export interface Tree2DData {
  nodes: TreeNode[]
  edges: TreeEdge[]
}

/* ------------------------------------------------------------------ visual 判别联合 */

interface VisualBase {
  id: string
  title?: string
  hint?: string
}

export interface Surface3DVisual extends VisualBase {
  kind: 'surface3d'
  data: Surface3DData
}
export interface Cloud3DVisual extends VisualBase {
  kind: 'cloud3d'
  data: Cloud3DData
}
export interface Vector3DVisual extends VisualBase {
  kind: 'vector3d'
  data: Vector3DData
}
export interface Line2DVisual extends VisualBase {
  kind: 'line2d'
  data: Line2DData
}
export interface BarsVisual extends VisualBase {
  kind: 'bars'
  data: BarsData
}
export interface MatrixVisual extends VisualBase {
  kind: 'matrix'
  data: MatrixData
}
export interface Tree2DVisual extends VisualBase {
  kind: 'tree2d'
  data: Tree2DData
}

/** §2 全部 7 种：按 `kind` 收窄，`data` 自动得到精确类型 */
export type Visual =
  | Surface3DVisual
  | Cloud3DVisual
  | Vector3DVisual
  | Line2DVisual
  | BarsVisual
  | MatrixVisual
  | Tree2DVisual

export type VisualKind = Visual['kind']
export type VisualDataOf<K extends VisualKind> = Extract<Visual, { kind: K }>['data']
export type VisualOf<K extends VisualKind> = Extract<Visual, { kind: K }>

/** 3D 的三种（共用 Scene3D 引擎），用于 `is3DKind()` */
export const KINDS_3D: VisualKind[] = ['surface3d', 'cloud3d', 'vector3d']
/** 2D SVG 的四种 */
export const KINDS_2D: VisualKind[] = ['line2d', 'bars', 'matrix', 'tree2d']

export function is3DKind(kind: VisualKind): boolean {
  return KINDS_3D.includes(kind)
}

/* ------------------------------------------------------------------ /fit 响应 */

export interface SeriesRow {
  id: string
  label: string
  x: number[]
  y: number[]
  xLabel?: string
  yLabel?: string
}

export interface TableRow {
  name: string
  value?: string
  truth?: string
  delta?: string
  note?: string
}

export interface TableCard {
  id: string
  title: string
  rows: TableRow[]
}

/** metrics 的键由 `METRIC_SPEC` 决定，值可能是 null（后端非有限数→null）；契约示例里还有 epoch/note */
export type MetricValue = number | string | null
export type Metrics = Record<string, MetricValue>

export interface FitResult {
  key: string
  /** 'numpy' | 'torch' | 'mock' */
  backend: string
  elapsedMs?: number
  steps: number
  seed: number
  params: Record<string, number | string | null>
  metrics: Metrics
  series: SeriesRow[]
  table: TableCard[]
  visuals: Visual[]
  /** /step 端点会带 resumed:true */
  resumed?: boolean
  declaredVisuals?: string[]
  missingVisuals?: string[]
  /** 前端注入：这一份结果来自离线 fixture */
  mock?: boolean
}

/* ------------------------------------------------------------------ 教案与目录 */

export interface FormulaVar {
  sym: string
  /** sym 的 LaTeX 形式（后端 loader 转录或教案手写），空则回退显示 sym */
  latex?: string
  zh: string
  /** §4：公式要配「代入真实数字的算例」 */
  example?: string
}

export interface Formula {
  /** 教案原文，Unicode 写法，也是 latex 缺失时的回退显示 */
  text: string
  /** KaTeX 源码；displayMode 渲染 */
  latex?: string
  vars: FormulaVar[]
}

export interface DerivationStep {
  title: string
  body: string
  formula?: string
  latex?: string
}

export interface Term {
  term: string
  full?: string
  explain: string
  /** /api/glossary 汇总时带上：哪些算法讲到它 */
  keys?: string[]
}

export interface ParamOption {
  value: number
  label: string
}

/** 与 `catalog.PARAM_SPECS` 一一对应；有 `options` 即离散选择 */
export interface ParamSpec {
  id: string
  label: string
  min: number
  max: number
  step: number
  default: number
  hint?: string
  options?: ParamOption[]
  type?: 'number' | 'int' | 'choice'
}

export interface Preset {
  id: string
  label: string
  params: Record<string, number>
}

/** `catalog.VISUAL_SPEC` 的一项 */
export interface VisualSpec {
  id: string
  kind: VisualKind
  title: string
  hint?: string
}

export interface MetricSpec {
  id: string
  label: string
}

export interface Quiz {
  q: string
  options: string[]
  answer: number
  why?: string
}

export type ItemStatus = 'ready' | 'outline'

export interface CatalogItem {
  key: string
  name: string
  status: ItemStatus
  difficulty: number
  tags: string[]
  tagline?: string
}

export interface Family {
  key: string
  name: string
  color: string
  blurb: string
  items: CatalogItem[]
}

export interface Catalog {
  families: Family[]
  readyCount?: number
  totalCount?: number
}

/** GET /api/algorithms/{key} */
export interface Algorithm {
  key: string
  name: string
  family: string
  familyName?: string
  color?: string
  status: ItemStatus
  difficulty: number
  tags: string[]
  tagline: string
  story: string
  formula: Formula
  intuition: string[]
  derivation: DerivationStep[]
  terms: Term[]
  pitfalls: string[]
  seeAlso: string[]
  quiz: Quiz | null
  params: ParamSpec[]
  presets: Preset[]
  metrics: MetricSpec[]
  visuals: VisualSpec[]
  hasSim?: boolean
  contentError?: string
  missingText?: string[]
}

export interface EnvInfo {
  python: string
  numpy: string | null
  torch: { available: boolean; version: string | null; device: string | null }
  hint: string | null
}

export interface GlossaryPayload {
  terms: Term[]
  count: number
}

/** GET /api/algorithms（列表） */
export interface AlgorithmList {
  items: Array<Pick<Algorithm, 'key' | 'name' | 'tagline' | 'family' | 'familyName' | 'color' | 'difficulty' | 'tags' | 'status'>>
}

/** GET /api/summary */
export interface SummaryPayload {
  total: number
  ready: number
  families: Array<Pick<Family, 'key' | 'name' | 'color'>>
  incompleteLessons: Array<{ key: string; missing: string[] }>
}
