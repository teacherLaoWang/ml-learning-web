/**
 * vector3d 的世界构建器（契约 §2 vector3d）：箭头条目 + 点。
 *
 * 动的方式：每支箭头沿自身方向跑一颗「流向球」（相位错开），
 * 虚线箭头额外做呼吸式明暗；箭头标签用底板 sprite 并按索引错开 lane。
 */
import * as THREE from 'three'
import type { AxisRange, Vector3DData } from '../types'
import { PlotFrame, SPHERE_GEO, boundsFromPoints, buildFloorAndAxes } from './frame'
import type { SceneEngine } from './engine'
import { labelColor } from '../utils/palette'
import { clamp, safeNum } from '../utils/format'

export class VectorWorld {
  private group = new THREE.Group()
  private frame: PlotFrame
  private offs: Array<() => void> = []
  private flows: Array<{ a: THREE.Vector3; b: THREE.Vector3; speed: number }> = []
  private flowMesh: THREE.InstancedMesh | null = null
  private dummy = new THREE.Object3D()

  constructor(
    private engine: SceneEngine,
    private data: Vector3DData,
  ) {
    this.frame = new PlotFrame(this.computeBounds())
    this.build()
    engine.add(this.group)
    this.offs.push(engine.onTick((t) => this.tick(t)))
  }

  private computeBounds() {
    const pts: Array<{ x: number; y: number; z: number }> = []
    for (const a of this.data.arrows ?? []) {
      for (const v of [a.from, a.to]) pts.push({ x: v[0], y: v[1], z: v[2] })
    }
    for (const p of this.data.points ?? []) pts.push({ x: p.x, y: p.y, z: p.z })
    const ext = boundsFromPoints(pts)
    const pad = 0.12
    return {
      ...ext,
      zmin: ext.zmin - (ext.zmax - ext.zmin) * pad,
      zmax: ext.zmax + (ext.zmax - ext.zmin) * pad,
    }
  }

  private axesOf(): { x: AxisRange; y: AxisRange; z: AxisRange } {
    const e = this.frame.ext
    const a = this.data.axes
    return {
      x: { label: a?.x ?? 'x', min: e.xmin, max: e.xmax },
      y: { label: a?.y ?? 'y', min: e.ymin, max: e.ymax },
      z: { label: a?.z ?? 'z', min: e.zmin, max: e.zmax },
    }
  }

  private build() {
    const f = this.frame
    this.group.add(
      buildFloorAndAxes(f, this.axesOf(), (text, pos, opts) => {
        const handle = this.engine.addLabel(text, opts?.style ?? {}, pos, opts?.lane ?? 0)
        this.offs.push(() => handle.dispose())
      }),
    )

    const arrows = this.data.arrows ?? []
    arrows.forEach((a, i) => {
      const from = f.toScene(safeNum(a.from[0]), safeNum(a.from[1]), safeNum(a.from[2]))
      const to = f.toScene(safeNum(a.to[0]), safeNum(a.to[1]), safeNum(a.to[2]))
      const dir = to.clone().sub(from)
      const len = dir.length()
      if (len < 1e-4) return
      const color = new THREE.Color(a.color ?? labelColor(i, i))
      if (a.dash) {
        const geo = new THREE.BufferGeometry().setFromPoints([from, to])
        const line = new THREE.Line(geo, new THREE.LineDashedMaterial({ color, dashSize: 0.09, gapSize: 0.06, transparent: true, opacity: 0.85 }))
        line.computeLineDistances()
        line.renderOrder = 5
        this.group.add(line)
        const cone = new THREE.Mesh(
          new THREE.ConeGeometry(0.026, 0.075, 14),
          new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.9, roughness: 0.5 }),
        )
        cone.position.copy(to)
        cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
        this.group.add(cone)
      } else {
        const head = new THREE.Mesh(
          new THREE.CylinderGeometry(0.011 * (a.width ?? 1), 0.011 * (a.width ?? 1), len * 0.9, 12),
          new THREE.MeshStandardMaterial({ color, roughness: 0.42, metalness: 0.12 }),
        )
        head.position.copy(from.clone().lerp(to, 0.45))
        head.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
        head.renderOrder = 5
        this.group.add(head)
        const cone = new THREE.Mesh(
          new THREE.ConeGeometry(0.032 * (a.width ?? 1), 0.1 * Math.min(1.4, len), 16),
          new THREE.MeshStandardMaterial({ color, roughness: 0.4, metalness: 0.12 }),
        )
        cone.position.copy(to)
        cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize())
        cone.renderOrder = 5
        this.group.add(cone)
      }
      this.flows.push({ a: from, b: to, speed: 0.34 + 0.08 * (i % 4) })
      if (a.label) {
        const anchor = new THREE.Object3D()
        anchor.position.copy(to.clone().lerp(from, 0.06))
        this.group.add(anchor)
        // 索引 → lane：多支箭头共点时标签竖直错开，不叠字
        const handle = this.engine.addLabel(a.label, { bold: !a.dash, accent: a.color ?? labelColor(i, i) }, anchor, i % 5)
        this.offs.push(() => handle.dispose())
      }
    })

    if (this.flows.length) {
      const mesh = new THREE.InstancedMesh(
        SPHERE_GEO,
        new THREE.MeshBasicMaterial({ color: 0xfff3c4, transparent: true, opacity: 0.95 }),
        this.flows.length,
      )
      mesh.renderOrder = 8
      this.flowMesh = mesh
      this.group.add(mesh)
    }

    const pts = this.data.points ?? []
    if (pts.length) {
      const inst = new THREE.InstancedMesh(SPHERE_GEO, new THREE.MeshStandardMaterial({ roughness: 0.5 }), pts.length)
      pts.forEach((p, i) => {
        this.dummy.position.copy(f.toScene(p.x, p.y, p.z))
        this.dummy.scale.setScalar(clamp(0.014 * safeNum(p.size, 1) + 0.012, 0.008, 0.05))
        this.dummy.updateMatrix()
        inst.setMatrixAt(i, this.dummy.matrix)
        inst.setColorAt(i, new THREE.Color(labelColor(p.label ?? 0, i)))
      })
      inst.instanceMatrix.needsUpdate = true
      if (inst.instanceColor) inst.instanceColor.needsUpdate = true
      inst.renderOrder = 6
      this.group.add(inst)
    }
  }

  private tick(time: number) {
    if (!this.flowMesh) return
    for (let i = 0; i < this.flows.length; i++) {
      const f = this.flows[i]
      const t = (time * f.speed + i / Math.max(1, this.flows.length)) % 1
      this.dummy.position.copy(f.a).lerp(f.b, t)
      this.dummy.scale.setScalar(0.012 + 0.014 * Math.sin(Math.PI * t))
      this.dummy.updateMatrix()
      this.flowMesh.setMatrixAt(i, this.dummy.matrix)
    }
    this.flowMesh.instanceMatrix.needsUpdate = true
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
    this.flowMesh = null
  }
}
