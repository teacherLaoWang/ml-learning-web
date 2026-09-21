/** 调色：与后端 `app/ml/util.py` 的 PALETTE 保持一致，图例颜色才对得上。 */

export const PALETTE = [
  '#2563eb', '#ea580c', '#0d9488', '#db2777', '#7c3aed',
  '#4f46e5', '#16a34a', '#b45309', '#0891b2', '#be123c',
]

export function colorOf(i: number | string | undefined | null): string {
  if (typeof i === 'number' && Number.isFinite(i)) return PALETTE[Math.abs(Math.trunc(i)) % PALETTE.length]
  if (typeof i === 'string') {
    if (i.startsWith('#')) return i
    let h = 0
    for (let i2 = 0; i2 < i.length; i2++) h = (h * 31 + i.charCodeAt(i2)) | 0
    return PALETTE[Math.abs(h) % PALETTE.length]
  }
  return PALETTE[0]
}

/** 类别标签 → 稳定的颜色（legend 缺色时兜底） */
export function labelColor(label: number | string | undefined, index: number): string {
  if (typeof label === 'number' && Number.isFinite(label)) return colorOf(label)
  return PALETTE[index % PALETTE.length]
}

export interface RGB {
  r: number
  g: number
  b: number
}

export function hexToRgb(hex: string): RGB {
  let h = hex.replace('#', '').trim()
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  const n = parseInt(h.slice(0, 6) || '000000', 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

export function rgbCss(c: RGB, a = 1): string {
  return a >= 1 ? `rgb(${c.r|0},${c.g|0},${c.b|0})` : `rgba(${c.r|0},${c.g|0},${c.b|0},${a})`
}

export function mixRgb(a: RGB, b: RGB, t: number): RGB {
  return { r: a.r + (b.r - a.r) * t, g: a.g + (b.g - a.g) * t, b: a.b + (b.b - a.b) * t }
}

export function mixHex(a: string, b: string, t: number): string {
  const c = mixRgb(hexToRgb(a), hexToRgb(b), t)
  return `#${[c.r, c.g, c.b].map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('')}`
}

/** 文字在该底色上是否可读（用于标签底板配色决策） */
export function isDark(hex: string): boolean {
  const { r, g, b } = hexToRgb(hex)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.55
}

function ramp(stops: string[], t: number): RGB {
  const n = stops.length - 1
  const x = Math.max(0, Math.min(0.999999, t)) * n
  const i = Math.floor(x)
  return mixRgb(hexToRgb(stops[i]), hexToRgb(stops[i + 1]), x - i)
}

const VIRIDIS = ['#410d79', '#322f80', '#235194', '#1d728e', '#299279', '#5cb25d', '#a5cf41', '#f0f921']
const TURBO = ['#2b1a75', '#1568b3', '#2ab7a9', '#8ade5a', '#e6d047', '#e58b33', '#bc3a1d', '#7a140f']
const COOLWARM = ['#2b5fc0', '#7ba6e8', '#cfe0f5', '#f7f7f7', '#f5cdbf', '#e08a72', '#b8331f']

/** 高度/数值 → 颜色。'height' 用于曲面顶点色，'diverge' 用于相关/混淆矩阵 */
export function colormap(t: number, kind: 'viridis' | 'turbo' | 'diverge' = 'viridis'): RGB {
  if (kind === 'diverge') return ramp(COOLWARM, (t + 1) / 2)
  return ramp(kind === 'turbo' ? TURBO : VIRIDIS, t)
}

export function colormapCss(t: number, kind: 'viridis' | 'turbo' | 'diverge' = 'viridis', a = 1): string {
  return rgbCss(colormap(t, kind), a)
}

export const SCENE = {
  bg: '#0d1424',
  bgTop: '#16223c',
  grid: '#2a3b5c',
  axisX: '#f26d6d',
  axisY: '#6de19a',
  axisZ: '#6db8f2',
  path: '#ffd166',
  trail: '#ff8c42',
  ball: '#fff3c4',
  contour: '#9fb6dd',
  contourHot: '#ffe08a',
  plate: 'rgba(255,255,255,0.93)',
  plateBorder: 'rgba(13,20,36,0.5)',
  plateText: '#101a2c',
}
