/**
 * cloud3d 的世界构建器（契约 §2 cloud3d）。
 *
 * 动的东西（硬要求 1）：
 *  - 给了 centroids 就演「点被吸入最近质心」：progress 驱动、每个点带自己的相位
 *  - boundary 的零/阈值的等值线用 flow shader 沿弧长流动
 *  - projection：半透明平面 + 法线箭头 + 每个点到平面的落点连线，连线上有 traveling 小球
 *  - 类别标签挂在各类质心上，随点云一起旋转（底板 sprite，永远不被点/线穿）
 */
import * as THREE from 'three'
import type { AxisRange, Cloud3DData, CloudPoint, LegendItem } from '../types'
import { PlotFrame, SPHERE_GEO, boundsFromGrid, boundsFromPoints, buildFloorAndAxes, contourLines, contourMesh, surfaceGeometry, surfaceWireframe } from './frame'
import type { SceneEngine } from './engine'
import { colormap, labelColor } from '../utils/palette'
import { clamp, easeInOutSine, safeNum } from '../utils/format'

export interface CloudWorldHooks {
  progress: () => number
}

interface Prepared {
  base: THREE.Vector3[]
  target: THREE.Vector3[]
  color: THREE.Color[]
  phase: number[]
  radius: number
}

export class CloudWorld {
  private group = new THREE.Group()
  private frame: PlotFrame
  private offs: Array<() => void> = []
  private prepared: Prepared | null = null
  private inst: THREE.InstancedMesh | null = null
  private pulse: THREE.InstancedMesh | null = null
  private contourMats: THREE.ShaderMaterial[] = []
  private dummy = new THREE.Object3D()
  private legend: LegendItem[] = []

  constructor(
    private engine: SceneEngine,
    private data: Cloud3DData,
    private hooks: CloudWorldHooks,
  ) {
    this.frame = new PlotFrame(this.computeBounds())
    this.build()
    engine.add(this.group)
    this.offs.push(engine.onTick((t) => this.tick(t)))
  }

  /** 供面板画 HTML 图例 */
  getLegend(): LegendItem[] {
    return this.legend
  }

  private computeBounds() {
    const all: Array<{ x: number; y: number; z: number }> = [...(this.data.points ?? [])]
    for (const c of this.data.centroids ?? []) all.push({ x: c.x, y: c.y, z: c.z })
    for (const h of this.data.hulls ?? []) for (const p of h.points ?? []) all.push({ x: p[0], y: p[1], z: p[2] })
    const ext = boundsFromPoints(all)
    const b = this.data.boundary
    if (b) {
      const g = boundsFromGrid(b.grid, b.axes)
      ext.xmin = Math.min(ext.xmin, g.xmin)
      ext.xmax = Math.max(ext.xmax, g.xmax)
      ext.ymin = Math.min(ext.ymin, g.ymin)
      ext.ymax = Math.max(ext.ymax, g.ymax)
      ext.zmin = Math.min(ext.zmin, g.zmin)
      ext.zmax = Math.max(ext.zmax, g.zmax)
    }
    return ext
  }

  private axesOf(): { x: AxisRange; y: AxisRange; z: AxisRange } {
    const e = this.frame.ext
    const b = this.data.boundary?.axes
    return {
      x: b?.x ?? { label: 'x', min: e.xmin, max: e.xmax },
      y: b?.y ?? { label: 'y', min: e.ymin, max: e.ymax },
      z: b?.z ?? { label: 'z', min: e.zmin, max: e.zmax },
    }
  }

  private build() {
    const d = this.data
    const f = this.frame
    const axes = this.axesOf()
    this.group.add(
      buildFloorAndAxes(f, axes, (text, pos, opts) => {
        const handle = this.engine.addLabel(text, opts?.style ?? {}, pos, opts?.lane ?? 0)
        this.offs.push(() => handle.dispose())
      }),
    )

    this.legend = d.legend?.length
      ? d.legend.map((l) => ({ label: String(l.label), color: l.color }))
      : uniqueLabels(d.points).map((l, i) => ({ label: `label ${l}`, color: labelColor(typeof l === 'number' ? l : i, i) }))

    if (d.boundary) this.buildBoundary(d.boundary)
    if (d.hulls?.length) this.buildHulls(d.hulls)
    if (d.projection) this.buildProjection(d.projection.origin, d.projection.normal, d.projection.label)
    this.buildPoints()
    this.buildClassLabels()
  }

  /* ------------------------------------------------------------ 分割面 */

  private buildBoundary(b: NonNullable<Cloud3DData['boundary']>) {
    const f = this.frame
    const geom = surfaceGeometry(b.grid, f, {
      colorize: (t) => {
        const c = colormap(clamp(t, 0, 1), 'turbo')
        return new THREE.Color().setStyle(`rgb(${Math.round(c.r)},${Math.round(c.g)},${Math.round(c.b)})`)
      },
    })
    if (geom) {
      const mesh = new THREE.Mesh(
        geom,
        new THREE.MeshStandardMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 0.42,
          roughness: 0.55,
          metalness: 0.02,
          side: THREE.DoubleSide,
          depthWrite: false,
        }),
      )
      mesh.renderOrder = 3
      this.group.add(mesh)
      const wire = surfaceWireframe(b.grid, f, '#7f98c4')
      if (wire) {
        ;(wire.material as THREE.LineBasicMaterial).opacity = 0.3
        this.group.add(wire)
      }
    }
    if (b.contour0) {
      const level = b.level ?? 0
      const line = contourMesh(contourLines(b.grid, level), f, level, {
        color: '#ffe08a',
        hot: '#fff8e1',
        period: 0.4,
      })
      if (line) {
        line.renderOrder = 9
        this.group.add(line)
        const shader = line.userData.material as THREE.ShaderMaterial | undefined
        if (shader) this.contourMats.push(shader)
      }
    }
  }

  private buildHulls(hulls: NonNullable<Cloud3DData['hulls']>) {
    for (const h of hulls) {
      const pts = (h.points ?? []).map((p) => this.frame.toScene(p[0], p[1], p[2]))
      if (pts.length < 2) continue
      const geo = new THREE.BufferGeometry().setFromPoints(pts)
      const color = h.color ?? labelColor(typeof h.label === 'number' ? h.label : 0, 0)
      const isPath = h.mode === 'path'
      // 轨迹不能闭合成圈：path 用不折返的 Line，loop（凸包轮廓）才用 LineLoop
      const line = isPath
        ? new THREE.Line(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9 }))
        : new THREE.LineLoop(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.85 }))
      line.renderOrder = 5
      this.group.add(line)
      if (isPath) {
        // 轨迹末端 = 收敛后的质心；标名交给 centroids（同一点上不再叠第二个标签）
        const knob = new THREE.Mesh(
          new THREE.SphereGeometry(0.03, 14, 10),
          new THREE.MeshBasicMaterial({ color }),
        )
        knob.position.copy(pts[pts.length - 1])
        knob.renderOrder = 6
        this.group.add(knob)
      }
    }
  }

  /* --------------------------------------------------------- 投影平面 */

  private buildProjection(origin: number[], normal: number[], label?: string) {
    const n = new THREE.Vector3(safeNum(normal[0], 0), safeNum(normal[2], 0), -safeNum(normal[1], 0))
    if (n.lengthSq() < 1e-9) n.set(0, 1, 0)
    n.normalize()
    const o = new THREE.Vector3(this.frame.sx(safeNum(origin[0])), this.frame.sy(safeNum(origin[2])), this.frame.sz(safeNum(origin[1])))
    const size = Math.max(this.frame.w, this.frame.d) * 0.98
    const plane = new THREE.Mesh(
      new THREE.PlaneGeometry(size, size),
      new THREE.MeshStandardMaterial({
        color: new THREE.Color('#8ab4ff'),
        transparent: true,
        opacity: 0.17,
        side: THREE.DoubleSide,
        roughness: 0.9,
        depthWrite: false,
      }),
    )
    plane.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n)
    plane.position.copy(o)
    plane.renderOrder = 2
    this.group.add(plane)

    const arrow = new THREE.ArrowHelper(n, o, size * 0.42, 0xf0f9ff, size * 0.09, size * 0.06)
    this.group.add(arrow)
    if (label) {
      const handle = this.engine.addLabel(label, { bold: true }, arrow.position, 0)
      this.offs.push(() => handle.dispose())
    }

    // 落点 + 垂线 + 沿线跑动的小球
    const pts = this.data.points ?? []
    const sample = pts.filter((_, i) => i % Math.max(1, Math.ceil(pts.length / 26)) === 0)
    const positions: number[] = []
    for (const p of sample) {
      const v = this.frame.toScene(p.x, p.y, p.z)
      const dist = v.clone().sub(o).dot(n)
      const foot = v.clone().addScaledVector(n, -dist)
      positions.push(v.x, v.y, v.z, foot.x, foot.y, foot.z)
    }
    if (positions.length) {
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
      const lines = new THREE.LineSegments(
        geo,
        new THREE.LineBasicMaterial({ color: 0x9fb6dd, transparent: true, opacity: 0.55, depthWrite: false }),
      )
      lines.renderOrder = 4
      this.group.add(lines)

      const pulse = new THREE.InstancedMesh(SPHERE_GEO, new THREE.MeshBasicMaterial({ color: 0xfff3c4, transparent: true, opacity: 0.95 }), sample.length)
      pulse.renderOrder = 8
      for (let i = 0; i < sample.length; i++) {
        const v = this.frame.toScene(sample[i].x, sample[i].y, sample[i].z)
        const dist = v.clone().sub(o).dot(n)
        const foot = v.clone().addScaledVector(n, -dist)
        ;(pulse.userData.ends ??= []).push({ a: v, b: foot })
        this.dummy.position.copy(v)
        this.dummy.scale.setScalar(0.016)
        this.dummy.updateMatrix()
        pulse.setMatrixAt(i, this.dummy.matrix)
      }
      this.pulse = pulse
      this.group.add(pulse)

      const ghost = new THREE.InstancedMesh(
        SPHERE_GEO,
        new THREE.MeshStandardMaterial({ color: new THREE.Color('#0d9488'), roughness: 0.5, transparent: true, opacity: 0.9 }),
        sample.length,
      )
      ghost.renderOrder = 6
      for (let i = 0; i < sample.length; i++) {
        const ends = (pulse.userData.ends as Array<{ a: THREE.Vector3; b: THREE.Vector3 }>)[i]
        this.dummy.position.copy(ends.b)
        this.dummy.scale.setScalar(0.026)
        this.dummy.updateMatrix()
        ghost.setMatrixAt(i, this.dummy.matrix)
      }
      this.group.add(ghost)
    }
  }

  /* -------------------------------------------------------------- 点云 */

  private buildPoints() {
    const pts = this.data.points ?? []
    if (!pts.length) return
    const f = this.frame
    const centroids = (this.data.centroids ?? []).map((c) => f.toScene(c.x, c.y, c.z))
    const base: THREE.Vector3[] = []
    const target: THREE.Vector3[] = []
    const color: THREE.Color[] = []
    const phase: number[] = []
    const labels = pts.map((p) => p.label)
    const uniq = uniqueLabels(pts)
    pts.forEach((p, i) => {
      const v = f.toScene(p.x, p.y, p.z)
      base.push(v)
      let dest = v.clone()
      if (centroids.length) {
        let best = 0
        let bestD = Infinity
        centroids.forEach((c, ci) => {
          const d2 = c.distanceToSquared(v)
          if (d2 < bestD) {
            bestD = d2
            best = ci
          }
        })
        dest = centroids[best].clone()
      }
      target.push(dest)
      const idx = uniq.indexOf(labels[i] ?? 0)
      const hex = this.legend[idx]?.color ?? labelColor(labels[i] as number, idx < 0 ? 0 : idx)
      color.push(new THREE.Color(hex))
      phase.push((i % 17) / 17)
    })
    const radius = clamp(0.028 * (this.data.collapse === undefined ? 1 : 1.05), 0.014, 0.06)
    const inst = new THREE.InstancedMesh(SPHERE_GEO, new THREE.MeshStandardMaterial({ roughness: 0.42, metalness: 0.08 }), pts.length)
    for (let i = 0; i < pts.length; i++) {
      inst.setColorAt(i, color[i])
      this.dummy.position.copy(base[i])
      this.dummy.scale.setScalar(radius * scaleOf(pts[i]))
      this.dummy.updateMatrix()
      inst.setMatrixAt(i, this.dummy.matrix)
    }
    inst.instanceMatrix.needsUpdate = true
    if (inst.instanceColor) inst.instanceColor.needsUpdate = true
    inst.renderOrder = 6
    this.inst = inst
    this.prepared = { base, target, color, phase, radius }
    this.group.add(inst)

    // 质心本身：大号空心球 + 标签
    for (const c of this.data.centroids ?? []) {
      const pos = f.toScene(c.x, c.y, c.z)
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.055, 18, 14),
        new THREE.MeshStandardMaterial({
          color: new THREE.Color(this.legendColorOf(c.label)),
          emissive: new THREE.Color(this.legendColorOf(c.label)),
          emissiveIntensity: 0.4,
          roughness: 0.35,
        }),
      )
      mesh.position.copy(pos)
      mesh.scale.setScalar(clamp(c.size ?? 1, 0.5, 2.4))
      mesh.renderOrder = 7
      this.group.add(mesh)
      if (c.label !== undefined) {
        const handle = this.engine.addLabel(`中心 ${c.label}`, { bold: true, accent: this.legendColorOf(c.label) }, mesh, 0)
        this.offs.push(() => handle.dispose())
      }
    }
  }

  private legendColorOf(label: number | string | undefined): string {
    const uniq = uniqueLabels(this.data.points ?? [])
    const idx = uniq.indexOf(label ?? 0)
    return this.legend[Math.max(0, idx)]?.color ?? labelColor(typeof label === 'number' ? label : 0, Math.max(0, idx))
  }

  private buildClassLabels() {
    const pts = this.data.points ?? []
    const uniq = uniqueLabels(pts)
    if (uniq.length > 6 || this.data.centroids?.length) return
    uniq.forEach((label, i) => {
      const sum = new THREE.Vector3()
      let n = 0
      pts.forEach((p) => {
        if ((p.label ?? 0) === label) {
          sum.add(this.frame.toScene(p.x, p.y, p.z))
          n++
        }
      })
      if (!n) return
      const anchor = new THREE.Object3D()
      anchor.position.copy(sum.divideScalar(n))
      this.group.add(anchor)
      const handle = this.engine.addLabel(`label ${label}`, { accent: this.legend[i]?.color, bold: true }, anchor, i % 3)
      this.offs.push(() => handle.dispose())
    })
  }

  /* --------------------------------------------------------------- 每帧 */

  private tick(time: number) {
    for (const mat of this.contourMats) mat.uniforms.uPhase.value = (time * 0.18) % 1
    const progress = clamp(this.hooks.progress(), 0, 1)
    if (this.inst && this.prepared) {
      const { base, target, radius, phase } = this.prepared
      const hasCentroids = (this.data.centroids?.length ?? 0) > 0
      for (let i = 0; i < base.length; i++) {
        const p = hasCentroids ? clamp((progress * 1.35 - 0.3 * phase[i]) / 1.05, 0, 1) : 0
        const k = easeInOutSine(p) * clamp(this.data.collapse ?? 0.85, 0, 1)
        this.dummy.position.copy(base[i]).lerp(target[i], k)
        // 呼吸式微缩放：让静态点云也有生命（但不喧宾夺主）
        const bob = 1 + 0.06 * Math.sin(time * 1.7 + i * 0.7)
        this.dummy.scale.setScalar(radius * bob)
        this.dummy.updateMatrix()
        this.inst.setMatrixAt(i, this.dummy.matrix)
      }
      this.inst.instanceMatrix.needsUpdate = true
    }
    if (this.pulse) {
      const ends = this.pulse.userData.ends as Array<{ a: THREE.Vector3; b: THREE.Vector3 }> | undefined
      if (ends) {
        for (let i = 0; i < ends.length; i++) {
          const t = (time * 0.55 + i / Math.max(1, ends.length)) % 1
          this.dummy.position.copy(ends[i].a).lerp(ends[i].b, t)
          this.dummy.scale.setScalar(0.013 + 0.012 * Math.sin(Math.PI * t))
          this.dummy.updateMatrix()
          this.pulse.setMatrixAt(i, this.dummy.matrix)
        }
        this.pulse.instanceMatrix.needsUpdate = true
      }
    }
  }

  dispose() {
    for (const off of this.offs) off()
    this.offs = []
    this.engine.remove(this.group)
    this.group.traverse((o) => {
      const mesh = o as THREE.Mesh & { material?: THREE.Material | THREE.Material[] }
      if (mesh.geometry && !mesh.geometry.userData.shared) mesh.geometry.dispose()
      const mats = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []
      for (const m of mats) m.dispose()
      const inst = o as THREE.InstancedMesh
      if (inst.isInstancedMesh) inst.dispose()
    })
    this.inst = null
  }
}

function uniqueLabels(pts: CloudPoint[]): Array<number | string> {
  const out: Array<number | string> = []
  for (const p of pts) {
    const l = p.label ?? 0
    if (!out.includes(l)) out.push(l)
  }
  return out.sort((a, b) => (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b))))
}

function scaleOf(p: CloudPoint): number {
  return clamp(1 + (safeNum(p.size, 1) - 1) * 0.45, 0.5, 2.6)
}
