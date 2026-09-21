/**
 * three.js 场景的数据层：数据坐标 → 场景坐标、曲面几何、等高线（marching squares）、坐标轴与底板网格。
 *
 * 右手系约定（契约 §0）：数据 (x, y, z) 映射为场景 (X, Y=up, Z)
 *   X = sx(x), Y = sy(z), Z = -sy_(y)  —— 用 (x, z, −y) 保证与后端一致不镜像。
 */
import * as THREE from 'three'
import type { AxisRange, GridData, Num3 } from '../types'
import { SCENE, colormap } from '../utils/palette'
import { clamp, normalize, safeNum, sampleIndices } from '../utils/format'
import type { LabelStyle } from './labels'

export const PLOT = { W: 2.7, D: 2.7, H: 1.35 }

export interface DataBounds {
  xmin: number
  xmax: number
  ymin: number
  ymax: number
  zmin: number
  zmax: number
}

export type AddLabel = (text: string, pos: THREE.Vector3, opts?: { lane?: number; style?: LabelStyle }) => void

function spread(lo: number, hi: number, pad = 0.06): [number, number] {
  let a = safeNum(lo, -1)
  let b = safeNum(hi, 1)
  if (!Number.isFinite(a) || !Number.isFinite(b)) return [-1, 1]
  if (b - a < 1e-9) {
    a -= 0.5
    b += 0.5
  }
  const d = (b - a) * pad
  return [a - d, b + d]
}

/** 由任意点集/网格求数据显示范围（cloud3d 顶层没有 axes，只能自算） */
export interface XYZ {
  x?: number
  y?: number
  z?: number
}

export function boundsFromPoints(pts: XYZ[]): DataBounds {
  let xmin = Infinity
  let xmax = -Infinity
  let ymin = Infinity
  let ymax = -Infinity
  let zmin = Infinity
  let zmax = -Infinity
  for (const p of pts) {
    const x = safeNum(p.x, 0)
    const y = safeNum(p.y, 0)
    const z = safeNum(p.z, 0)
    if (x < xmin) xmin = x
    if (x > xmax) xmax = x
    if (y < ymin) ymin = y
    if (y > ymax) ymax = y
    if (z < zmin) zmin = z
    if (z > zmax) zmax = z
  }
  if (!Number.isFinite(xmin)) return { xmin: -1, xmax: 1, ymin: -1, ymax: 1, zmin: 0, zmax: 1 }
  const [x0, x1] = spread(xmin, xmax)
  const [y0, y1] = spread(ymin, ymax)
  return { xmin: x0, xmax: x1, ymin: y0, ymax: y1, zmin, zmax }
}

export function boundsFromGrid(grid: GridData, axes?: { x?: AxisRange; y?: AxisRange; z?: AxisRange }): DataBounds {
  const xs = grid.x ?? []
  const ys = grid.y ?? []
  let zmin = Infinity
  let zmax = -Infinity
  for (const row of grid.z ?? []) {
    for (const v of row) {
      const n = safeNum(v, 0)
      if (n < zmin) zmin = n
      if (n > zmax) zmax = n
    }
  }
  if (!Number.isFinite(zmin)) {
    zmin = 0
    zmax = 1
  }
  const zx = axes?.z
  const axisOr = (axis: AxisRange | undefined, a: number, b: number): [number, number] =>
    axis && Number.isFinite(axis.min) && Number.isFinite(axis.max) ? [axis.min, axis.max] : [a, b]
  const [xr, xt] = axisOr(axes?.x, safeNum(xs[0], -1), safeNum(xs[xs.length - 1], 1))
  const [yr, yt] = axisOr(axes?.y, safeNum(ys[0], -1), safeNum(ys[ys.length - 1], 1))
  return {
    xmin: xr,
    xmax: xt,
    ymin: yr,
    ymax: yt,
    zmin: zx?.min !== undefined && Number.isFinite(zx.min) ? zx.min : zmin,
    zmax: zx?.max !== undefined && Number.isFinite(zx.max) ? zx.max : zmax,
  }
}

/** 数据 → 场景的线性映射；所有 3D 组件都通过它摆东西，保证轴/面/点严格对齐 */
export class PlotFrame {
  readonly ext: DataBounds
  readonly w: number
  readonly d: number
  readonly h: number

  constructor(ext: DataBounds, size: { W?: number; D?: number; H?: number } = {}) {
    const ord = (a: number, b: number): [number, number] => (b < a ? [b, a] : [a, b])
    const [x0, x1] = ord(safeNum(ext.xmin, -1), safeNum(ext.xmax, 1))
    const [y0, y1] = ord(safeNum(ext.ymin, -1), safeNum(ext.ymax, 1))
    const [z0, z1] = ord(safeNum(ext.zmin, 0), safeNum(ext.zmax, 1))
    this.ext = {
      xmin: x0,
      xmax: x1 === x0 ? x0 + 1 : x1,
      ymin: y0,
      ymax: y1 === y0 ? y0 + 1 : y1,
      zmin: z0,
      zmax: z1 === z0 ? z0 + 1 : z1,
    }
    this.w = size.W ?? PLOT.W
    this.d = size.D ?? PLOT.D
    this.h = size.H ?? PLOT.H
  }

  sx(x: number): number {
    return (normalize(safeNum(x), this.ext.xmin, this.ext.xmax) - 0.5) * this.w
  }

  /** 数据 y → 场景 Z（取负保持右手系） */
  sz(y: number): number {
    return (0.5 - normalize(safeNum(y), this.ext.ymin, this.ext.ymax)) * this.d
  }

  sy(z: number): number {
    return (normalize(safeNum(z), this.ext.zmin, this.ext.zmax) - 0.5) * this.h
  }

  get halfH(): number {
    return this.h / 2
  }

  toScene(x: number, y: number, z: number): THREE.Vector3 {
    return new THREE.Vector3(this.sx(x), this.sy(z), this.sz(y))
  }

  /** 数据空间向量 → 场景方向（只缩放不平移，用于箭头/梯度） */
  dirToScene(dx: number, dy: number, dz: number): THREE.Vector3 {
    const kx = this.w / (this.ext.xmax - this.ext.xmin)
    const ky = this.d / (this.ext.ymax - this.ext.ymin)
    const kz = this.h / (this.ext.zmax - this.ext.zmin)
    return new THREE.Vector3(dx * kx, dz * kz, -dy * ky)
  }

  /** 数据长度 → 场景水平尺度（取 x/y 平均，避免各向异性夸张） */
  levelScale(): number {
    const kx = this.w / (this.ext.xmax - this.ext.xmin)
    const ky = this.d / (this.ext.ymax - this.ext.ymin)
    return (kx + ky) / 2
  }

  zOf(p: THREE.Vector3): number {
    return (p.y / this.h + 0.5) * (this.ext.zmax - this.ext.zmin) + this.ext.zmin
  }
}

/* ---------------------------------------------------------------- 网格几何 */

export interface SurfaceGeomOptions {
  /** 顶点色：t 归一化后送 colormap */
  colorize?: (t: number, x: number, y: number, z: number) => THREE.Color
}

/** 由 grid.z[j][i] 构造带顶点色的曲面（§3：网格线 → 实体 → 轴 → 文字） */
export function surfaceGeometry(grid: GridData, frame: PlotFrame, opts: SurfaceGeomOptions = {}): THREE.BufferGeometry | null {
  const xs = grid.x ?? []
  const ys = grid.y ?? []
  const zRows = grid.z ?? []
  const nx = xs.length
  const ny = ys.length
  if (nx < 2 || ny < 2) return null

  const pos = new Float32Array(nx * ny * 3)
  const col = new Float32Array(nx * ny * 3)
  const [lo, hi] = frame.ext.zmax - frame.ext.zmin < 1e-12 ? [0, 1] : [frame.ext.zmin, frame.ext.zmax]
  let p = 0
  for (let j = 0; j < ny; j++) {
    const row = zRows[j] ?? []
    for (let i = 0; i < nx; i++) {
      const z = safeNum(row[i], frame.ext.zmin)
      pos[p] = frame.sx(xs[i])
      pos[p + 1] = frame.sy(z)
      pos[p + 2] = frame.sz(ys[j])
      const c = opts.colorize
        ? opts.colorize(normalize(z, lo, hi), xs[i], ys[j], z)
        : new THREE.Color().setStyle(`rgb(${rgbStr(normalize(z, lo, hi))})`)
      col[p] = c.r
      col[p + 1] = c.g
      col[p + 2] = c.b
      p += 3
    }
  }
  const idx: number[] = []
  for (let j = 0; j < ny - 1; j++) {
    for (let i = 0; i < nx - 1; i++) {
      const a = j * nx + i
      const b = a + 1
      const c = a + nx
      const d = c + 1
      idx.push(a, c, b, b, c, d)
    }
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
  geo.setIndex(idx)
  geo.computeVertexNormals()
  return geo
}

function rgbStr(t: number): string {
  const c = colormap(clamp(t, 0, 1), 'viridis')
  return `${Math.round(c.r)},${Math.round(c.g)},${Math.round(c.b)}`
}

/** 曲面上的网格线（抽稀到 ~24 条，密度太高会糊） */
export function surfaceWireframe(grid: GridData, frame: PlotFrame, color = SCENE.grid): THREE.LineSegments | null {
  const xs = grid.x ?? []
  const ys = grid.y ?? []
  const zRows = grid.z ?? []
  if (xs.length < 2 || ys.length < 2) return null
  const iIdx = sampleIndices(xs.length, 22)
  const jIdx = sampleIndices(ys.length, 22)
  const pts: number[] = []
  const lift = 0.006
  const at = (i: number, j: number) => {
    const z = safeNum(zRows[j]?.[i], frame.ext.zmin)
    return [frame.sx(xs[i]), frame.sy(z) + lift, frame.sz(ys[j])] as Num3
  }
  for (const i of iIdx) {
    for (let j = 0; j < ys.length - 1; j++) {
      const a = at(i, j)
      const b = at(i, j + 1)
      pts.push(a[0], a[1], a[2], b[0], b[1], b[2])
    }
  }
  for (const j of jIdx) {
    for (let i = 0; i < xs.length - 1; i++) {
      const a = at(i, j)
      const b = at(i + 1, j)
      pts.push(a[0], a[1], a[2], b[0], b[1], b[2])
    }
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.5, depthWrite: false })
  const lines = new THREE.LineSegments(geo, mat)
  lines.renderOrder = 1
  return lines
}

/* ---------------------------------------------------------- 等高线 marching squares */

type Seg = [[number, number], [number, number]]

/** 单个 level 的等值线（数据空间折线，已尽量串接成链） */
export function contourLines(grid: GridData, level: number): Array<Array<[number, number]>> {
  const xs = grid.x ?? []
  const ys = grid.y ?? []
  const Z = grid.z ?? []
  if (xs.length < 2 || ys.length < 2) return []
  const segs: Seg[] = []
  const L = safeNum(level)
  const v = (i: number, j: number) => safeNum(Z[j]?.[i], L - 1)

  for (let j = 0; j < ys.length - 1; j++) {
    for (let i = 0; i < xs.length - 1; i++) {
      const c0 = v(i, j) > L
      const c1 = v(i + 1, j) > L
      const c2 = v(i + 1, j + 1) > L
      const c3 = v(i, j + 1) > L
      const code = (c0 ? 1 : 0) | (c1 ? 2 : 0) | (c2 ? 4 : 0) | (c3 ? 8 : 0)
      if (code === 0 || code === 15) continue
      const px = (xa: number, ya: number, va: number, vb: number, xb: number, yb: number) => {
        const t = Math.abs(vb - va) < 1e-12 ? 0.5 : clamp((L - va) / (vb - va), 0, 1)
        return [xa + (xb - xa) * t, ya + (yb - ya) * t] as [number, number]
      }
      const A = px(xs[i], ys[j], v(i, j), v(i + 1, j), xs[i + 1], ys[j])
      const B = px(xs[i + 1], ys[j], v(i + 1, j), v(i + 1, j + 1), xs[i + 1], ys[j + 1])
      const C = px(xs[i], ys[j + 1], v(i, j + 1), v(i + 1, j + 1), xs[i + 1], ys[j + 1])
      const D = px(xs[i], ys[j], v(i, j), v(i, j + 1), xs[i], ys[j + 1])
      switch (code) {
        case 1:
        case 14:
          segs.push([D, A])
          break
        case 2:
        case 13:
          segs.push([A, B])
          break
        case 3:
        case 12:
          segs.push([D, B])
          break
        case 4:
        case 11:
          segs.push([B, C])
          break
        case 6:
        case 9:
          segs.push([A, C])
          break
        case 7:
        case 8:
          segs.push([C, D])
          break
        case 5: {
          const center = (v(i, j) + v(i + 1, j) + v(i, j + 1) + v(i + 1, j + 1)) / 4
          if (center > L) segs.push([A, B], [C, D])
          else segs.push([D, A], [B, C])
          break
        }
        case 10: {
          const center = (v(i, j) + v(i + 1, j) + v(i, j + 1) + v(i + 1, j + 1)) / 4
          if (center > L) segs.push([D, A], [B, C])
          else segs.push([A, B], [C, D])
          break
        }
        default:
          break
      }
    }
  }
  return chainSegments(segs)
}

/** 把散线段接成折线链，便于沿弧长做「流动」高光 */
function chainSegments(segs: Seg[]): Array<Array<[number, number]>> {
  const key = (p: [number, number]) => `${p[0].toFixed(4)}|${p[1].toFixed(4)}`
  const map = new Map<string, number[]>()
  segs.forEach((s, i) => {
    for (const end of [0, 1]) {
      const k = key(s[end])
      const arr = map.get(k) ?? []
      arr.push(i * 2 + end)
      map.set(k, arr)
    }
  })
  const used = new Uint8Array(segs.length)
  const out: Array<Array<[number, number]>> = []
  for (let i = 0; i < segs.length; i++) {
    if (used[i]) continue
    used[i] = 1
    const chain: Array<[number, number]> = [segs[i][0], segs[i][1]]
    // 向前延伸
    for (let guard = 0; guard < segs.length; guard++) {
      const tail = chain[chain.length - 1]
      const cand = (map.get(key(tail)) ?? []).find((id) => !used[id >> 1])
      if (cand === undefined) break
      const si = cand >> 1
      const ei = cand & 1
      used[si] = 1
      chain.push(segs[si][ei === 0 ? 1 : 0])
    }
    // 向后延伸
    for (let guard = 0; guard < segs.length; guard++) {
      const head = chain[0]
      const cand = (map.get(key(head)) ?? []).find((id) => !used[id >> 1])
      if (cand === undefined) break
      const si = cand >> 1
      const ei = cand & 1
      used[si] = 1
      chain.unshift(segs[si][ei === 0 ? 1 : 0])
    }
    out.push(chain)
  }
  return out
}

/* --------------------------------------------------------- 坐标轴、底板网格、图例文字 */

export interface AxesOptions {
  x: AxisRange
  y: AxisRange
  z: AxisRange
  /** 刻度个数 */
  ticks?: number
}

/**
 * 画：底板网格 + 三条轴 + 轴名与刻度文字（全部走 AddLabel → sprite 带白色底板）。
 * 顺序（§3）：网格线在几何体之前，文字最后。
 */
export function buildFloorAndAxes(frame: PlotFrame, axes: AxesOptions, addLabel: AddLabel, tickValues?: { x?: number[]; y?: number[]; z?: number[] }): THREE.Group {
  const g = new THREE.Group()
  const { xmin, xmax, ymin, ymax, zmin } = frame.ext
  const yFloor = frame.sy(zmin) - 0.001
  const nTicks = axes.ticks ?? 4

  // ---- 底板网格（先画，最底层）
  const pts: number[] = []
  const gridMat = new THREE.LineBasicMaterial({ color: SCENE.grid, transparent: true, opacity: 0.55, depthWrite: false })
  const xt = tickValues?.x ?? ticksOf(axes.x, nTicks)
  const yt = tickValues?.y ?? ticksOf(axes.y, nTicks)
  for (const x of xt) {
    pts.push(frame.sx(x), yFloor, frame.sz(ymin), frame.sx(x), yFloor, frame.sz(ymax))
  }
  for (const y of yt) {
    pts.push(frame.sx(xmin), yFloor, frame.sz(y), frame.sx(xmax), yFloor, frame.sz(y))
  }
  const floorGeo = new THREE.BufferGeometry()
  floorGeo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  const floor = new THREE.LineSegments(floorGeo, gridMat)
  floor.renderOrder = 0
  g.add(floor)

  // ---- 三条轴（X 红 / Y 绿 / Z 蓝）
  const edges: Array<{ from: Num3; to: Num3; color: string }> = [
    { from: [xmin, ymin, zmin], to: [xmax, ymin, zmin], color: SCENE.axisX },
    { from: [xmin, ymin, zmin], to: [xmin, ymax, zmin], color: SCENE.axisY },
    { from: [xmin, ymin, zmin], to: [xmin, ymin, zmaxOf(frame)], color: SCENE.axisZ },
  ]
  for (const e of edges) {
    const geo = new THREE.BufferGeometry().setFromPoints([frame.toScene(...e.from), frame.toScene(...e.to)])
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: e.color, transparent: true, opacity: 0.95 }))
    line.renderOrder = 2
    g.add(line)
  }

  // ---- 文字：轴名 + 刻度值（lane 错开，避免同区域叠字）
  let lane = 0
  addLabel(axes.x.label, frame.toScene((xmin + xmax) / 2, ymin, zmin).add(new THREE.Vector3(0, -0.02, 0.16)), {
    lane: lane++,
    style: { bold: true, heightPx: 19 },
  })
  addLabel(axes.y.label, frame.toScene(xmin, (ymin + ymax) / 2, zmin).add(new THREE.Vector3(-0.14, -0.02, 0)), {
    lane: lane++,
    style: { bold: true, heightPx: 19 },
  })
  addLabel(`${axes.z.label}`, frame.toScene(xmin, ymin, (zminOf(frame) + zmaxOf(frame)) / 2).add(new THREE.Vector3(-0.16, 0, 0)), {
    lane: lane++,
    style: { bold: true, heightPx: 19 },
  })
  const zt = tickValues?.z ?? ticksOf({ label: '', min: zmin, max: zmaxOf(frame) }, nTicks)
  for (const x of xt.slice(0, 4)) {
    addLabel(fmtTick(x), frame.toScene(x, ymin, zmin), { lane: 1, style: { fontSize: 20, heightPx: 13, bold: false, plateColor: 'rgba(255,255,255,0.8)' } })
  }
  for (const y of yt.slice(0, 4)) {
    addLabel(fmtTick(y), frame.toScene(xmin, y, zmin), { lane: 1, style: { fontSize: 20, heightPx: 13, bold: false, plateColor: 'rgba(255,255,255,0.8)' } })
  }
  for (const z of zt.slice(0, 4)) {
    addLabel(fmtTick(z), frame.toScene(xmin, ymin, z), { lane: 2, style: { fontSize: 20, heightPx: 13, bold: false, plateColor: 'rgba(255,255,255,0.8)' } })
  }
  return g
}

function zmaxOf(frame: PlotFrame): number {
  return frame.ext.zmax
}
function zminOf(frame: PlotFrame): number {
  return frame.ext.zmin
}

export function ticksOf(axis: AxisRange, count: number): number[] {
  const lo = safeNum(axis.min, 0)
  const hi = safeNum(axis.max, 1)
  const out: number[] = []
  for (let i = 0; i <= count; i++) out.push(lo + ((hi - lo) * i) / count)
  return out
}

export function fmtTick(v: number): string {
  const a = Math.abs(v)
  if (a < 1e-4) return '0'
  if (a >= 1000) return v.toExponential(1)
  if (a >= 10) return v.toFixed(0)
  if (a >= 1) return v.toFixed(1)
  return v.toFixed(2)
}

/** 等高线 → 带弧长属性的 LineSegments（配合 flow shader 做相位流动） */
export function contourMesh(
  lines: Array<Array<[number, number]>>,
  frame: PlotFrame,
  level: number,
  opts: { color: string; hot: string; period?: number; width?: number },
): THREE.LineSegments | null {
  const pos: number[] = []
  const arc: number[] = []
  const period = opts.period ?? 0.55
  const lift = 0.008
  for (const chain of lines) {
    let acc = 0
    for (let i = 0; i < chain.length - 1; i++) {
      const a = chain[i]
      const b = chain[i + 1]
      const pa = frame.toScene(a[0], a[1], level)
      const pb = frame.toScene(b[0], b[1], level)
      const segLen = pa.distanceTo(pb)
      arc.push(acc / period, (acc + segLen) / period)
      acc += segLen
      pos.push(pa.x, pa.y + lift, pa.z, pb.x, pb.y + lift, pb.z)
    }
  }
  if (!pos.length) return null
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  geo.setAttribute('aArc', new THREE.Float32BufferAttribute(arc, 1))
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: {
      uPhase: { value: 0 },
      uBase: { value: new THREE.Color(opts.color) },
      uHot: { value: new THREE.Color(opts.hot) },
    },
    vertexShader: `attribute float aArc; varying float vArc;
void main(){ vArc = aArc; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform float uPhase; uniform vec3 uBase; uniform vec3 uHot; varying float vArc;
void main(){
  float w = fract(vArc - uPhase);
  float pulse = smoothstep(0.72, 0.92, w) * (1.0 - smoothstep(0.92, 1.0, w));
  vec3 c = mix(uBase, uHot, pulse);
  gl_FragColor = vec4(c, 0.55 + pulse * 0.45);
}`,
  })
  const mesh = new THREE.LineSegments(geo, mat)
  mesh.renderOrder = 3
  mesh.userData.material = mat
  return mesh
}

/**
 * 拖尾材质：静态折线 + 均匀参数 aT，播放头 uHead 扫过时点亮并留下渐隐尾巴。
 * surface3d 的下降轨迹与 cloud3d 的质心移动轨迹共用（动画一律由时间/播放头驱动）。
 */
export function makeTrailMaterial(colHead: string, colTail: string, span = 0.34): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: {
      uHead: { value: 0 },
      uSpan: { value: span },
      uColA: { value: new THREE.Color(colTail) },
      uColB: { value: new THREE.Color(colHead) },
    },
    vertexShader: `attribute float aT; varying float vT;
void main(){ vT = aT; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform float uHead; uniform float uSpan; uniform vec3 uColA; uniform vec3 uColB; varying float vT;
void main(){
  float behind = step(vT, uHead);
  float age = clamp((uHead - vT) / uSpan, 0.0, 1.0);
  float a = behind * (1.0 - age * age) * 0.95 + 0.05;
  gl_FragColor = vec4(mix(uColB, uColA, age), a);
}`,
  })
}

/** 折线顶点 → 带 aT 参数的几何（aT 均匀分布，配 makeTrailMaterial 用） */
export function trailGeometry(points: THREE.Vector3[]): THREE.BufferGeometry | null {
  const n = points.length
  if (n < 2) return null
  const pos: number[] = []
  const par: number[] = []
  for (let i = 0; i < n; i++) {
    pos.push(points[i].x, points[i].y, points[i].z)
    par.push(i / (n - 1))
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  geo.setAttribute('aT', new THREE.Float32BufferAttribute(par, 1))
  return geo
}

/** 值 → 最近网格线下标（后端 window.x/y 可能给格索引也可能给数据坐标，都能落位） */
export function nearestIndex(arr: number[], v: number | undefined): number {
  if (v === undefined || !Number.isFinite(v) || !arr.length) return 0
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < arr.length; i++) {
    const d = Math.abs(arr[i] - v)
    if (d < bestD) {
      bestD = d
      best = i
    }
  }
  return best
}

/** 圆点（cloud3d/vector3d 用的小球几何，全场景共享一份，靠 userData.shared 免被 dispose） */
export const SPHERE_GEO = new THREE.SphereGeometry(1, 14, 10)
SPHERE_GEO.userData.shared = true
