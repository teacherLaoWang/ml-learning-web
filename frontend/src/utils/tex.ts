/** KaTeX 排版：带缓存，解析失败返回 null 让调用方回退。 */
import katex from 'katex'

const cache = new Map<string, string | null>()

export function texToHtml(src: string, display: boolean): string | null {
  const key = `${display ? 'D' : 'I'}\u0000${src}`
  if (cache.has(key)) return cache.get(key) ?? null
  const trimmed = src.trim()
  if (!trimmed) {
    cache.set(key, null)
    return null
  }
  let html: string | null = null
  try {
    // throwOnError=false：模型写的坏公式只标红，不打断整段渲染
    html = katex.renderToString(trimmed, {
      displayMode: display,
      throwOnError: false,
      strict: false,
      output: 'html',
      errorColor: '#f87171',
    })
    if (/class="latex-error"|katex-error/.test(html)) html = null
  } catch {
    html = null
  }
  cache.set(key, html)
  return html
}

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string)
}

/** 把 `$...$` 从正文里切出来：偶数号定界，段内不许再出现 $。 */
export function splitMath(text: string): Array<{ math: boolean; v: string }> {
  const out: Array<{ math: boolean; v: string }> = []
  const re = /\$([^$\n]+)\$/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ math: false, v: text.slice(last, m.index) })
    out.push({ math: true, v: m[1] })
    last = m.index + m[0].length
  }
  if (last < text.length) out.push({ math: false, v: text.slice(last) })
  return out
}
