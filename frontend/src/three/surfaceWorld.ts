/**
 * surface3d 的世界构建器（契约 §2 surface3d）。
 *
 * 动画全由时间/播放头驱动（硬要求 1）：
 *  - 轨迹小球沿 path 折线插值（progress 由父组件的时间轴给）
 *  - 拖尾：静态折线 + shader 的 uHead 扫过 → 尾巴连续流动
 *  - 梯度箭头：每帧按当前点的 grad 反方向重画
 *  - 等高线：shader 里 uPhase 随时间推进，色带沿弧长流动
 *  - 卷积窗口：按帧逐格滑动（data.window 给了才画）
 */
import * as THREE from 'three'
import type { Surface3DData } from '../types'
import { PlotFrame, boundsFromGrid, buildFloorAndAxes, contourLines, contourMesh, surfaceGeometry, surfaceWireframe } from './frame'
import type { SceneEngine } from './engine'
import { SCENE, colormap } from '../utils/palette'
import { clamp, fmtNum, safeNum } from '../utils/format'

const UP = new THREE.Vector3(0, 1, 0)
const TRAIL_SPAN = 0.34

export interface SurfaceWorldHooks {
  progress: () => number
}

interface WinState {
  box: THREE.Mesh
  edges: THREE.LineSegments
  spanI: number
  spanJ: number
  stride: number
  cols: number
  rows: number
  xs: number[]
  ys: number[]
  z: number[][]
  sceneW: number
  sceneD: number
}

export class SurfaceWorld {
  private group = new THREE.Group()
  private frame: PlotFrame
  private offs: Array<() => void> = []
  private samples: THREE.Vector3[] = []
  private sampleSteps: number[] = []
  private trailMat: THREE.ShaderMaterial | null = null
  private contourMats: THREE.ShaderMaterial[] = []
  private ball: THREE.Mesh | null = null
  private ballGlow: THREE.Sprite | null = null
  private gradArrow: THREE.ArrowHelper | null = null
  private headLabel: ReturnType<SceneEngine['addLabel']> | null = null
  private headText = ''
  private win: WinState | null = null
  private headTick = 0   // 播放头读数节流计数器

  constructor(
    private engine: SceneEngine,
    private data: Surface3DData,
    private hooks: SurfaceWorldHooks,
  ) {
    this.frame = new PlotFrame(this.computeBounds())
    this.build()
    engine.add(this.group)
    this.offs.push(engine.onTick((t) => this.tick(t)))
  }

  private computeBounds() {
    const ext = boundsFromGrid(this.data.grid, this.data.axes)
    const extra: number[] = []
    for (const p of this.data.path ?? []) extra.push(p.z)
    if (this.data.optimum) extra.push(this.data.optimum.z)
    for (const m of this.data.markers ?? []) extra.push(m.z)
    if (extra.length) {
      ext.zmin = Math.min(ext.zmin, ...extra)
      ext.zmax = Math.max(ext.zmax, ...extra)
    }
    return ext
  }

  private build() {
    const d = this.data
    const f = this.frame
    // §3.1 层叠顺序：网格线 → 实体 → 轴 → 文字
    this.group.add(
      buildFloorAndAxes(f, { x: d.axes.x, y: d.axes.y, z: d.axes.z }, (text, pos, opts) => {
        const handle = this.engine.addLabel(text, opts?.style ?? {}, pos, opts?.lane ?? 0)
        this.offs.push(() => handle.dispose())
      }),
    )

    const geom = surfaceGeometry(d.grid, f, {
      colorize: (t) => {
        const c = colormap(clamp(t, 0, 1), 'viridis')
        return new THREE.Color().setStyle(`rgb(${Math.round(c.r)},${Math.round(c.g)},${Math.round(c.b)})`)
      },
    })
    if (geom) {
      const mesh = new THREE.Mesh(
        geom,
        new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.68, metalness: 0.06, side: THREE.DoubleSide }),
      )
      mesh.renderOrder = 4
      this.group.add(mesh)
      const wire = surfaceWireframe(d.grid, f)
      if (wire) this.group.add(wire)
    }

    for (const level of d.levels ?? []) {
      const line = contourMesh(contourLines(d.grid, level), f, level, { color: SCENE.contour, hot: SCENE.contourHot })
      if (!line) continue
      this.group.add(line)
      const shader = line.userData.material as THREE.ShaderMaterial | undefined
      if (shader) this.contourMats.push(shader)
    }

    this.buildPath()
    this.buildMarkers()
    this.buildWindow()
  }

  /* ------------------------------------------------- 轨迹：插值小球 + 拖尾 + 梯度 */

  private buildPath() {
    const path = this.data.path ?? []
    if (!path.length) return
    this.samples = path.map((p) => this.frame.toScene(p.x, p.y, p.z))
    this.sampleSteps = path.map((p) => safeNum(p.step, 0))
    const n = this.samples.length

    const pos: number[] = []
    const par: number[] = []
    for (let i = 0; i < n; i++) {
      const v = this.samples[i]
      pos.push(v.x, v.y, v.z)
      par.push(i / Math.max(1, n - 1))
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
    geo.setAttribute('aT', new THREE.Float32BufferAttribute(par, 1))

    const ghost = new THREE.Line(
      geo.clone(),
      new THREE.LineBasicMaterial({ color: 0x8ea4c8, transparent: true, opacity: 0.32, depthWrite: false }),
    )
    ghost.renderOrder = 5
    this.group.add(ghost)

    this.trailMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: {
        uHead: { value: 0 },
        uSpan: { value: TRAIL_SPAN },
        uColA: { value: new THREE.Color(SCENE.trail) },
        uColB: { value: new THREE.Color(SCENE.path) },
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
    const trail = new THREE.Line(geo, this.trailMat)
    trail.renderOrder = 6
    this.group.add(trail)

    const ball = new THREE.Mesh(
      new THREE.SphereGeometry(0.045, 18, 14),
      new THREE.MeshStandardMaterial({
        color: new THREE.Color(SCENE.ball),
        emissive: new THREE.Color('#ff9f1c'),
        emissiveIntensity: 0.75,
        roughness: 0.35,
      }),
    )
    ball.renderOrder = 7
    this.ball = ball
    this.group.add(ball)

    const glow = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glowTexture(),
        color: new THREE.Color(SCENE.path),
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    )
    glow.scale.setScalar(0.3)
    glow.renderOrder = 8
    this.ballGlow = glow
    this.group.add(glow)

    const arrow = new THREE.ArrowHelper(UP, new THREE.Vector3(), 0.25, 0x7cf0c4, 0.07, 0.05)
    ;(arrow.line.material as THREE.LineBasicMaterial).transparent = true
    ;(arrow.cone.material as THREE.MeshBasicMaterial).transparent = true
    this.gradArrow = arrow
    this.group.add(arrow)

    this.headLabel = this.engine.addLabel('t=0', { bold: true, heightPx: 17 }, ball, 1)
  }

  private headAt(progress: number) {
    const n = this.samples.length
    if (!n) return { pos: new THREE.Vector3(), t: 0, idx: 0 }
    const steps = this.sampleSteps
    const lastStep = steps[steps.length - 1] ?? 0
    const target = clamp(progress, 0, 1) * lastStep
    let i = 0
    while (i < n - 2 && steps[i + 1] < target) i++
    const j = Math.min(n - 1, i + 1)
    const a = steps[i]
    const b = steps[j]
    const f = b - a < 1e-9 ? 0 : clamp((target - a) / (b - a), 0, 1)
    return {
      pos: this.samples[i].clone().lerp(this.samples[j], f),
      t: clamp((i + f) / Math.max(1, n - 1), 0, 1),
      idx: i,
    }
  }

  private buildMarkers() {
    const list: Array<{ p: { x: number; y: number; z: number; label?: string; color?: string }; strong: boolean }> = []
    for (const m of this.data.markers ?? []) list.push({ p: m, strong: false })
    if (this.data.optimum) list.push({ p: this.data.optimum, strong: true })
    list.forEach((entry, i) => {
      const color = entry.p.color ?? (entry.strong ? '#16a34a' : '#f97316')
      const base = new THREE.Color(color)
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(entry.strong ? 0.05 : 0.036, 16, 12),
        new THREE.MeshStandardMaterial({ color: base, emissive: base, emissiveIntensity: 0.35, roughness: 0.4 }),
      )
      mesh.position.copy(this.frame.toScene(entry.p.x, entry.p.y, entry.p.z))
      mesh.renderOrder = 7
      this.group.add(mesh)
      if (entry.p.label) {
        // 索引 → lane，同区域多个标签沿相机 up 错开，避免叠字
        const handle = this.engine.addLabel(entry.p.label, { bold: entry.strong, accent: color }, mesh, i % 4)
        this.offs.push(() => handle.dispose())
      }
    })
  }

  /* --------------------------------------------------------- 卷积滑动框 */

  private buildWindow() {
    const w = this.data.window
    if (!w) return
    const g = this.data.grid
    const nx = g.x.length
    const ny = g.y.length
    if (nx < 3 || ny < 3) return
    // 后端 cnn 发的 size 是标量（核边长），契约也允许 [宽,高]：两种写法都要能吃下
    const [sw, sh] = Array.isArray(w.size) ? w.size : [w.size ?? 3, w.size ?? 3]
    const cw = clamp(Math.round(sw), 2, nx - 1)
    const ch = clamp(Math.round(sh), 2, ny - 1)
    const stride = clamp(Math.round(w.stride ?? 1), 1, 4)
    const cols = Math.max(1, Math.floor((nx - cw) / stride) + 1)
    const rows = Math.max(1, Math.floor((ny - ch) / stride) + 1)
    const sceneW = Math.abs(this.frame.sx(g.x[cw - 1]) - this.frame.sx(g.x[0])) || 0.2
    const sceneD = Math.abs(this.frame.sz(g.y[ch - 1]) - this.frame.sz(g.y[0])) || 0.2
    const boxGeo = new THREE.BoxGeometry(1, 1, 1)
    const box = new THREE.Mesh(
      boxGeo,
      new THREE.MeshBasicMaterial({ color: '#ffd166', transparent: true, opacity: 0.15, depthWrite: false }),
    )
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(boxGeo),
      new THREE.LineBasicMaterial({ color: '#ffd166', transparent: true, opacity: 0.95, depthWrite: false }),
    )
    box.renderOrder = 8
    edges.renderOrder = 8
    this.group.add(box)
    this.group.add(edges)
    this.win = {
      box,
      edges,
      spanI: cw - 1,
      spanJ: ch - 1,
      stride,
      cols,
      rows,
      xs: g.x,
      ys: g.y,
      z: g.z,
      sceneW,
      sceneD,
    }
  }

  /** 按「第几个窗口位置」摆放：逐格跳，不是平滑飘（更像真实卷积） */
  private placeWindow(index: number) {
    const win = this.win
    if (!win) return
    const cell = clamp(Math.floor(index), 0, win.cols * win.rows - 1)
    const i0 = (cell % win.cols) * win.stride
    const j0 = Math.floor(cell / win.cols) * win.stride
    let lo = Infinity
    let hi = -Infinity
    for (let j = j0; j <= Math.min(win.ys.length - 1, j0 + win.spanJ); j++) {
      const row = win.z[j] ?? []
      for (let i = i0; i <= Math.min(win.xs.length - 1, i0 + win.spanI); i++) {
        const v = safeNum(row[i], 0)
        if (v < lo) lo = v
        if (v > hi) hi = v
      }
    }
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
      lo = this.frame.ext.zmin
      hi = this.frame.ext.zmax
    }
    const cx = win.xs[Math.min(win.xs.length - 1, i0 + win.spanI / 2)]
    const cy = win.ys[Math.min(win.ys.length - 1, j0 + win.spanJ / 2)]
    const center = this.frame.toScene(cx, cy, 0)
    const yLo = Math.min(this.frame.sy(lo), this.frame.sy(hi))
    const yHi = Math.max(this.frame.sy(lo), this.frame.sy(hi)) + 0.025
    const h = Math.max(0.05, yHi - yLo)
    for (const obj of [win.box, win.edges]) {
      obj.scale.set(win.sceneW, h, win.sceneD)
      obj.position.set(center.x, yLo + h / 2, center.z)
    }
  }

  /* --------------------------------------------------------------- 每帧 */

  private tick(time: number) {
    for (const mat of this.contourMats) mat.uniforms.uPhase.value = (time * 0.16) % 1
    const progress = clamp(this.hooks.progress(), 0, 1)
    // 卷积滑动框不依赖轨迹：cnn 的两个曲面没有 path，若放在下面的早返回之后就永远停在原位
    if (this.win) this.placeWindow(progress * this.win.cols * this.win.rows)
    if (!this.trailMat || !this.samples.length) return
    this.trailMat.uniforms.uHead.value = progress
    const head = this.headAt(progress)
    if (this.ball) this.ball.position.copy(head.pos).addScaledVector(UP, 0.014)
    if (this.ballGlow) this.ballGlow.position.copy(head.pos)
    const point = this.data.path?.[head.idx]
    if (this.gradArrow && point) {
      const grad = point.grad ?? [0, 0]
      const dir = this.frame.dirToScene(-safeNum(grad[0]), -safeNum(grad[1]), 0)
      const mag = dir.length()
      if (mag > 1e-5) {
        this.gradArrow.position.copy(head.pos).addScaledVector(UP, 0.02)
        this.gradArrow.setDirection(dir.normalize())
        this.gradArrow.setLength(clamp(mag * 0.5, 0.09, 0.6), 0.062, 0.046)
        this.gradArrow.visible = true
      } else {
        this.gradArrow.visible = false
      }
    }
    if (this.headLabel && point) {
      const text = `t=${Math.round(safeNum(point.step, 0))} · L=${fmtNum(point.z, 3)}`
      // 重建一次标签 = 两张 canvas + 一张 CanvasTexture；播放时逐帧重建是最主要的掉帧与 GC 来源，
      // 所以每 4 帧才更新一次读数（肉眼看不出差别）
      this.headTick = (this.headTick + 1) % 4
      if (text !== this.headText && this.headTick === 0) {
        this.headText = text
        this.headLabel.setText(text)
      }
    }
  }

  dispose() {
    for (const off of this.offs) off()
    this.offs = []
    this.headLabel?.dispose()
    this.headLabel = null
    this.engine.remove(this.group)
    this.group.traverse((o) => {
      const mesh = o as THREE.Mesh & { material?: THREE.Material | THREE.Material[] }
      if (mesh.geometry && !mesh.geometry.userData.shared) mesh.geometry.dispose()
      const mats = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []
      for (const m of mats) {
        const withMap = m as THREE.Material & { map?: THREE.Texture }
        withMap.map?.dispose()
        m.dispose()
      }
    })
  }
}

let glowTex: THREE.Texture | null = null
function glowTexture(): THREE.Texture {
  if (glowTex) return glowTex
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const ctx = c.getContext('2d')!
  const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32)
  grad.addColorStop(0, 'rgba(255,255,255,0.95)')
  grad.addColorStop(0.35, 'rgba(255,209,102,0.55)')
  grad.addColorStop(1, 'rgba(255,209,102,0)')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, 64, 64)
  glowTex = new THREE.CanvasTexture(c)
  glowTex.userData.shared = true
  return glowTex
}
