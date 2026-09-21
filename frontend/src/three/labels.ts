/**
 * 3D 场景里的文字：一律用 canvas 纹理 sprite，白色圆角底板 + 细边框衬底。
 * 目的（硬要求 2）：文字绝不与线/点互相穿插遮挡——底板挡住后面的几何体，
 * 且 sprite 的 depthTest 关闭 + 高 renderOrder，永远画在最上层。
 */
import * as THREE from 'three'
import { SCENE } from '../utils/palette'
import { shortLabel } from '../utils/format'

const DPR = 2 // 纹理超采样，旋转时不虚

export interface LabelStyle {
  /** 字号（CSS px，纹理内） */
  fontSize?: number
  /** 目标屏幕高度（CSS px），引擎按相机距离换算成世界尺度 */
  heightPx?: number
  bold?: boolean
  /** 文字色 */
  color?: string
  /** 左侧色条（图例/类别色） */
  accent?: string
  /** 底板是否透明一点（次要信息） */
  plateColor?: string
  borderColor?: string
  /** 最长显示字符数 */
  maxChars?: number
  /** 锚点：'center' | 'bottom' | 'top' */
  anchor?: 'center' | 'bottom' | 'top'
}

export interface LabelArt {
  texture: THREE.Texture
  /** 纹理宽/高 */
  aspect: number
  heightPx: number
  sprite: THREE.Sprite
}

function roundRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, w / 2, h / 2)
  ctx.beginPath()
  ctx.moveTo(x + rr, y)
  ctx.lineTo(x + w - rr, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + rr)
  ctx.lineTo(x + w, y + h - rr)
  ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h)
  ctx.lineTo(x + rr, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - rr)
  ctx.lineTo(x, y + rr)
  ctx.quadraticCurveTo(x, y, x + rr, y)
  ctx.closePath()
}

/** 生成一张「底板 + 文字」纹理，同时给出宽高比供等比缩放 */
export function makeLabelArt(rawText: string, style: LabelStyle = {}): LabelArt {
  const fontSize = style.fontSize ?? 26
  const maxChars = style.maxChars ?? 22
  const text = shortLabel(rawText, maxChars)
  const bold = style.bold ?? true
  const font = `${bold ? '600 ' : ''}${fontSize}px -apple-system, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", system-ui, sans-serif`

  // 先量尺寸
  const probe = document.createElement('canvas').getContext('2d')!
  probe.font = font
  const textW = Math.ceil(probe.measureText(text).width)
  const accentW = style.accent ? 6 : 0
  const padX = 10
  const padY = 7
  const w = textW + accentW + padX * 2
  const h = fontSize + padY * 2

  const canvas = document.createElement('canvas')
  canvas.width = Math.ceil(w * DPR)
  canvas.height = Math.ceil(h * DPR)
  const ctx = canvas.getContext('2d')!
  ctx.scale(DPR, DPR)
  ctx.clearRect(0, 0, w, h)

  // 底板
  ctx.fillStyle = style.plateColor ?? SCENE.plate
  roundRectPath(ctx, 0.75, 0.75, w - 1.5, h - 1.5, 7)
  ctx.fill()
  ctx.lineWidth = 1.5
  ctx.strokeStyle = style.borderColor ?? SCENE.plateBorder
  ctx.stroke()

  if (style.accent) {
    ctx.fillStyle = style.accent
    roundRectPath(ctx, 4, 4, 4, h - 8, 2)
    ctx.fill()
  }

  ctx.font = font
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = style.color ?? SCENE.plateText
  ctx.fillText(text, padX + accentW, h / 2 + 0.5)

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 2
  texture.needsUpdate = true

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false, // 文字永远在最上层，不与线/点互穿
    depthWrite: false,
    toneMapped: false,
  })
  const sprite = new THREE.Sprite(material)
  sprite.renderOrder = 1200
  sprite.center =
    style.anchor === 'bottom'
      ? new THREE.Vector2(0.5, 0)
      : style.anchor === 'top'
        ? new THREE.Vector2(0.5, 1)
        : new THREE.Vector2(0.5, 0.5)

  return { texture, aspect: w / h, heightPx: style.heightPx ?? (style.fontSize ? fontSize * 0.62 : 17), sprite }
}

export function disposeLabelArt(art: LabelArt | null | undefined) {
  if (!art) return
  art.texture.dispose()
  ;(art.sprite.material as THREE.SpriteMaterial).dispose()
  art.sprite.removeFromParent()
}
