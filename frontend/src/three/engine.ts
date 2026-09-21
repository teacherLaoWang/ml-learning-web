/**
 * SceneEngine：three.js 通用容器（Scene3D.vue 的内部实现）。
 *
 * 负责的事：
 *  - 透视相机 + OrbitControls（触摸友好）+ 环境光/方向光
 *  - requestAnimationFrame + 时间累加器：动画一律由时间驱动（硬要求 2）
 *  - 多来源暂停（页面隐藏 / 面板不在视口 / 用户手动暂停）→ 真的停掉 rAF，不烧 CPU（硬要求 3）
 *  - 文字 sprite 按相机距离保持恒定屏幕高度，并按 lane 沿相机 up 错开，避免叠字（硬要求 2）
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { disposeLabelArt, makeLabelArt, type LabelArt, type LabelStyle } from './labels'
import { SCENE } from '../utils/palette'
import { clamp } from '../utils/format'

export type TickFn = (time: number, dt: number) => void

export type PauseSource = 'hidden' | 'offscreen' | 'manual' | 'noData'

export interface LabelHandle {
  sprite: THREE.Sprite
  setText(text: string): void
  setLane(lane: number): void
  setAnchor(target: THREE.Object3D | THREE.Vector3 | null): void
  show(visible: boolean): void
  dispose(): void
}

interface SpriteRec {
  art: LabelArt
  lane: number
  anchor: THREE.Object3D | THREE.Vector3 | null
  text: string
  style: LabelStyle
}

const DEFAULT_CAM = new THREE.Vector3(3.55, 2.4, 3.95)

/* 自动化布局检查用的只读登记处：本机访问时由 main.ts 挂到 window.__ml3d */
const live = new Set<SceneEngine>()
export function liveEngines(): SceneEngine[] {
  return [...live]
}

export class SceneEngine {
  readonly scene = new THREE.Scene()
  readonly camera: THREE.PerspectiveCamera
  readonly controls: OrbitControls
  readonly renderer: THREE.WebGLRenderer
  /** 子组件把几何体挂到这里 */
  readonly root = new THREE.Group()
  time = 0
  width = 1
  height = 1
  onError: ((msg: string) => void) | null = null

  private container: HTMLElement
  private sprites: SpriteRec[] = []
  private ticks = new Set<TickFn>()
  private pauses = new Set<PauseSource>()
  private rafId: number | null = null
  private lastTs = 0
  private ro: ResizeObserver | null = null
  private disposed = false
  private up = new THREE.Vector3(0, 1, 0)
  private tmp = new THREE.Vector3()
  private _autoRotate = false

  constructor(container: HTMLElement) {
    live.add(this)
    this.container = container
    const w = Math.max(1, container.clientWidth)
    const h = Math.max(1, container.clientHeight)
    this.width = w
    this.height = h

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    this.renderer.setSize(w, h, false)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    const canvas = this.renderer.domElement
    canvas.style.display = 'block'
    canvas.style.width = '100%'
    canvas.style.height = '100%'
    canvas.style.touchAction = 'none'
    container.appendChild(canvas)
    canvas.addEventListener('webglcontextlost', this.onContextLost)

    this.scene.background = makeBackdrop()
    this.scene.add(this.root)

    this.camera = new THREE.PerspectiveCamera(46, w / h, 0.05, 120)
    this.camera.position.copy(DEFAULT_CAM)

    this.controls = new OrbitControls(this.camera, canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.09
    this.controls.rotateSpeed = 0.85
    this.controls.zoomSpeed = 0.85
    this.controls.panSpeed = 0.6
    this.controls.minDistance = 1.4
    this.controls.maxDistance = 16
    this.controls.maxPolarAngle = Math.PI * 0.95
    this.controls.autoRotateSpeed = 1.0
    this.controls.target.set(0, 0, 0)
    this.controls.update()

    this.addLights()

    this.ro = new ResizeObserver(() => this.resize())
    this.ro.observe(container)
  }

  private onContextLost = (ev: Event) => {
    ev.preventDefault()
    this.stopLoop()
    this.onError?.('WebGL 上下文丢失（可能切换了显卡/休眠）。刷新页面即可恢复。')
  }

  private addLights() {
    this.scene.add(new THREE.HemisphereLight(0xdce9ff, 0x111826, 1.0))
    const key = new THREE.DirectionalLight(0xffffff, 1.5)
    key.position.set(4, 6, 3)
    this.scene.add(key)
    const fill = new THREE.DirectionalLight(0x8ab4ff, 0.5)
    fill.position.set(-5, 2.5, -4)
    this.scene.add(fill)
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.34))
  }

  /* ------------------------------------------------------------ 生命周期 */

  resize() {
    if (this.disposed) return
    const w = Math.max(1, this.container.clientWidth)
    const h = Math.max(1, this.container.clientHeight)
    if (w === this.width && h === this.height) return
    this.width = w
    this.height = h
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.renderer.setSize(w, h, false)
    this.renderOnce()
  }

  setPause(source: PauseSource, paused: boolean) {
    if (paused) this.pauses.add(source)
    else this.pauses.delete(source)
    if (this.paused) {
      this.stopLoop()
      this.renderOnce()
    } else {
      this.startLoop()
    }
  }

  get paused(): boolean {
    return this.pauses.size > 0
  }

  get running(): boolean {
    return this.rafId !== null
  }

  set autoRotate(on: boolean) {
    this._autoRotate = on
    this.controls.autoRotate = on
    if (!this.paused) this.startLoop()
  }

  get autoRotate(): boolean {
    return this._autoRotate
  }

  startLoop() {
    if (this.disposed || this.rafId !== null || this.paused) return
    this.lastTs = 0
    this.rafId = requestAnimationFrame(this.frame)
  }

  stopLoop() {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId)
      this.rafId = null
    }
  }

  private frame = (ts: number) => {
    if (this.disposed) {
      this.rafId = null
      return
    }
    if (this.paused) {
      this.rafId = null
      return
    }
    const dt = this.lastTs ? Math.min(0.05, (ts - this.lastTs) / 1000) : 0.016
    this.lastTs = ts
    this.time += dt
    for (const fn of [...this.ticks]) fn(this.time, dt)
    this.updateSprites()
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
    this.rafId = requestAnimationFrame(this.frame)
  }

  /** 只画一帧（暂停状态下改了几何体也要能刷新） */
  renderOnce() {
    if (this.disposed) return
    this.updateSprites()
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }

  onTick(fn: TickFn): () => void {
    this.ticks.add(fn)
    return () => {
      this.ticks.delete(fn)
    }
  }

  add(obj: THREE.Object3D) {
    this.root.add(obj)
    this.renderOnce()
  }

  remove(obj: THREE.Object3D) {
    this.root.remove(obj)
    this.renderOnce()
  }

  /* ------------------------------------------------------------ 文字 sprite */

  /** 注册一个带白色底板的 3D 文字；anchor 给对象则每帧跟随 */
  addLabel(text: string, style: LabelStyle = {}, anchor?: THREE.Object3D | THREE.Vector3 | null, lane = 0): LabelHandle {
    const art = makeLabelArt(text, style)
    const rec: SpriteRec = { art, lane, anchor: anchor ?? null, text, style }
    if (anchor) art.sprite.position.copy(this.worldOf(anchor))
    this.root.add(art.sprite)
    this.sprites.push(rec)
    this.updateSprites()
    const self = this

    const handle: LabelHandle = {
      sprite: art.sprite,
      setText(next: string) {
        if (next === rec.text) return
        const idx = self.sprites.indexOf(rec)
        if (idx < 0) return
        const pos = rec.art.sprite.position.clone()
        disposeLabelArt(rec.art)
        const rebuilt = makeLabelArt(next, rec.style)
        rebuilt.sprite.position.copy(pos)
        rec.text = next
        rec.art = rebuilt
        self.sprites[idx] = rec
        self.root.add(rebuilt.sprite)
        handle.sprite = rebuilt.sprite
        self.updateSprites()
      },
      setLane(l: number) {
        rec.lane = l
        self.updateSprites()
      },
      setAnchor(target) {
        rec.anchor = target
      },
      show(visible: boolean) {
        rec.art.sprite.visible = visible
        self.renderOnce()
      },
      dispose() {
        const idx = self.sprites.indexOf(rec)
        if (idx >= 0) self.sprites.splice(idx, 1)
        disposeLabelArt(rec.art)
      },
    }
    return handle
  }

  /** 画布 CSS 像素尺寸，供布局检查使用 */
  viewportSize(): { w: number; h: number } {
    return { w: this.width, h: this.height }
  }

  /**
   * 把每个可见文字 sprite 投影成屏幕包围盒（CSS 像素、相对画布左上角）。
   * 供自动化检查「文字是否互相叠字 / 是否跑出画布」，不参与渲染逻辑。
   */
  labelScreenRects(): Array<{ text: string; x: number; y: number; w: number; h: number }> {
    const out: Array<{ text: string; x: number; y: number; w: number; h: number }> = []
    const v = new THREE.Vector3()
    const c = new THREE.Vector3()
    for (const rec of this.sprites) {
      const sp = rec.art.sprite
      if (!sp.visible) continue
      sp.getWorldPosition(v)
      const before = v.clone()
      v.project(this.camera)
      if (v.z > 1) continue
      const cx = (v.x * 0.5 + 0.5) * this.width
      const cy = (1 - (v.y * 0.5 + 0.5)) * this.height
      c.copy(before).addScaledVector(new THREE.Vector3(1, 0, 0), sp.scale.x / 2)
        .addScaledVector(new THREE.Vector3(0, 1, 0), sp.scale.y / 2)
      c.project(this.camera)
      const hw = Math.abs((c.x * 0.5 + 0.5) * this.width - cx)
      const hh = Math.abs((1 - (c.y * 0.5 + 0.5)) * this.height - cy)
      out.push({ text: rec.text, x: cx - hw, y: cy - hh, w: hw * 2, h: hh * 2 })
    }
    return out
  }

  private worldOf(target: THREE.Object3D | THREE.Vector3): THREE.Vector3 {
    if ((target as THREE.Object3D).isObject3D) {
      this.tmp.set(0, 0, 0)
      ;(target as THREE.Object3D).localToWorld(this.tmp)
      return this.tmp
    }
    return this.tmp.copy(target as THREE.Vector3)
  }

  private updateSprites() {
    if (!this.sprites.length) return
    const halfFov = THREE.MathUtils.degToRad(this.camera.fov / 2)
    this.up.set(0, 1, 0).applyQuaternion(this.camera.quaternion)
    const pxPerWorldAt1 = this.height / (2 * Math.tan(halfFov))
    for (const rec of this.sprites) {
      const { art, anchor } = rec
      if (anchor) art.sprite.position.copy(this.worldOf(anchor))
      const dist = art.sprite.position.distanceTo(this.camera.position)
      const worldH = clamp((art.heightPx / pxPerWorldAt1) * dist, 0.028, 1.3)
      art.sprite.scale.set(worldH * art.aspect, worldH, 1)
      if (rec.lane) art.sprite.position.addScaledVector(this.up, worldH * 1.18 * rec.lane)
    }
  }

  /* ------------------------------------------------------------ 视角 */

  resetCamera() {
    this.camera.position.copy(DEFAULT_CAM)
    this.controls.target.set(0, 0, 0)
    this.controls.update()
    this.renderOnce()
  }

  /** 顶视/正视/侧视：点云与曲面靠换视角看遮挡关系 */
  setView(kind: 'top' | 'front' | 'side' | 'default') {
    const d = DEFAULT_CAM.length()
    const p =
      kind === 'top'
        ? new THREE.Vector3(0.02, d, 0.02)
        : kind === 'front'
          ? new THREE.Vector3(0, 0.4, d)
          : kind === 'side'
            ? new THREE.Vector3(d, 0.4, 0.02)
            : DEFAULT_CAM.clone()
    this.camera.position.copy(p)
    this.controls.target.set(0, 0, 0)
    this.controls.update()
    this.renderOnce()
  }

  focus(point: THREE.Vector3) {
    this.controls.target.copy(point)
    this.controls.update()
    this.renderOnce()
  }

  dispose() {
    if (this.disposed) return
    this.disposed = true
    live.delete(this)
    this.stopLoop()
    this.ro?.disconnect()
    this.ro = null
    this.ticks.clear()
    for (const rec of this.sprites) disposeLabelArt(rec.art)
    this.sprites = []
    for (const child of [...this.root.children]) {
      this.root.remove(child)
      child.traverse((o) => {
        const mesh = o as THREE.Mesh & { isSprite?: boolean; material?: THREE.Material | THREE.Material[] }
        if (mesh.geometry && !mesh.geometry.userData.shared) mesh.geometry.dispose()
        const mat = mesh.material
        const list = Array.isArray(mat) ? mat : mat ? [mat] : []
        for (const m of list) {
          if (!m.userData.shared) {
            const withMap = m as THREE.Material & { map?: THREE.Texture }
            withMap.map?.dispose()
            m.dispose()
          }
        }
      })
    }
    const canvas = this.renderer.domElement
    canvas.removeEventListener('webglcontextlost', this.onContextLost)
    this.controls.dispose()
    this.renderer.dispose()
    if (canvas.parentElement === this.container) this.container.removeChild(canvas)
    const bg = this.scene.background
    if (bg instanceof THREE.Texture) bg.dispose()
    this.scene.background = null
  }
}

/** 深色渐变背景：让白色标签底板足够跳出来 */
function makeBackdrop(): THREE.Texture {
  const c = document.createElement('canvas')
  c.width = 8
  c.height = 256
  const ctx = c.getContext('2d')!
  const grad = ctx.createLinearGradient(0, 0, 0, 256)
  grad.addColorStop(0, SCENE.bgTop)
  grad.addColorStop(1, SCENE.bg)
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, 8, 256)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.userData.shared = true
  return tex
}
