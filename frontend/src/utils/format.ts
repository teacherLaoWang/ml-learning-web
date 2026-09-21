/** 小工具：数值格式化与动画插值。全部纯函数，供组件直接调用。 */

export function clamp(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return lo
  return v < lo ? lo : v > hi ? hi : v
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function smoothstep(t: number): number {
  const x = clamp(t, 0, 1)
  return x * x * (3 - 2 * x)
}

export function easeOutCubic(t: number): number {
  const x = clamp(t, 0, 1)
  return 1 - Math.pow(1 - x, 3)
}

export function easeInOutSine(t: number): number {
  return -(Math.cos(Math.PI * clamp(t, 0, 1)) - 1) / 2
}

/** 安全的 number：NaN/Infinity/null → 0 */
export function safeNum(v: unknown, fallback = 0): number {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : fallback
}

/** 把 [lo,hi] 里的值映到 0..1（lo==hi 时给 0.5） */
export function normalize(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return 0
  if (hi - lo < 1e-12) return 0.5
  return clamp((v - lo) / (hi - lo), 0, 1)
}

/** 教学站里最常出现的数字显示：绝对值很大用科学计数，很小给 3 位有效 */
export function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const a = Math.abs(n)
  if (a === 0) return '0'
  if (a >= 1e5 || a < 1e-4) return n.toExponential(2)
  if (a >= 1000) return n.toFixed(0)
  if (a >= 100) return n.toFixed(Math.max(0, digits - 3))
  if (a >= 1) return n.toFixed(Math.max(0, digits - 1))
  return n.toFixed(digits + 1)
}

/** 坐标轴刻度专用：去掉无意义的尾随零（0.4000 → 0.4，20.00 → 20），
 *  否则长刻度串会向左撞进竖排轴名那一列 */
export function fmtTick(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const a = Math.abs(n)
  if (a !== 0 && (a >= 1e6 || a < 1e-4)) return n.toExponential(1)
  const s = n.toFixed(digits)
  return s.includes('.') ? s.replace(/\.?0+$/, '') : s
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return Math.round(Number(v)).toLocaleString('en-US')
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return `${(Number(v) * 100).toFixed(digits)}%`
}

/** 参数值显示：整数值不显示小数 */
export function fmtParam(v: number | string | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') return v
  return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(4)))
}

/** 数组等距抽稀（含首尾），用于把 45×45 网格降到渲染友好的采样密度 */
export function sampleIndices(n: number, cap: number): number[] {
  if (n <= cap) return Array.from({ length: n }, (_, i) => i)
  const out: number[] = []
  for (let i = 0; i < cap; i++) out.push(Math.round((i * (n - 1)) / (cap - 1)))
  return Array.from(new Set(out)).sort((a, b) => a - b)
}

/** 整数刻度：给 SVG 坐标轴用 */
export function niceTicks(lo: number, hi: number, count = 5): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi - lo < 1e-12) return [lo]
  const span = hi - lo
  const rawStep = span / Math.max(1, count)
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)))
  const norm = rawStep / mag
  const step = (norm >= 5 ? 5 : norm >= 2 ? 2 : norm >= 1.5 ? 1.5 : 1) * mag
  const start = Math.ceil(lo / step) * step
  const ticks: number[] = []
  for (let v = start; v <= hi + step * 1e-6; v += step) ticks.push(Number(v.toFixed(10)))
  return ticks
}

export function debounce<A extends unknown[]>(fn: (...args: A) => void, ms: number): ((...args: A) => void) & { cancel(): void } {
  let timer: ReturnType<typeof setTimeout> | null = null
  const wrapped = (...args: A) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      fn(...args)
    }, ms)
  }
  wrapped.cancel = () => {
    if (timer) clearTimeout(timer)
    timer = null
  }
  return wrapped
}

export function shortText(s: string, max = 46): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

/** 3D 标签必须短：太长会糊成一片，交给 HTML 图例 */
export function shortLabel(s: string, max = 18): string {
  const t = s.replace(/\s+/g, ' ').trim()
  return t.length > max ? `${t.slice(0, max - 1)}…` : t
}

export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}
