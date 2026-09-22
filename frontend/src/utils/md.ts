/**
 * 极简 Markdown → HTML，只覆盖模型回答里真正常见的东西：
 * 段落、`- ` 列表、**粗体**、`行内代码`、$...$ 行内公式、$$...$$ 独立公式。
 *
 * 不引第三方 parser 的原因：这里的输入来自外部模型，自己写反而能保证
 * 除 KaTeX 产物之外的所有文本都先经过 HTML 转义，不留注入面。
 */
import { escapeHtml, texToHtml } from './tex'

const PH_HEAD = '\u0000'
const PH_TAIL = '\u0001'

function inline(text: string): string {
  let s = escapeHtml(text)
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  s = s.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
  return s
}

export function mdToHtml(src: string): string {
  const atoms: string[] = []
  let text = src ?? ''

  // 公式先整块摘出来（$$ 优先，避免被 $ 单条规则切碎）。
  // 独立公式前后各补一个空行：模型经常写成「一句话\n$$x$$\n下一句」甚至紧挨着，
  // 不补就会把整块塞进普通段落里当行内公式排版。
  text = text.replace(/\$\$([^$]+)\$\$/g, (_m, tex: string) => {
    atoms.push(texToHtml(tex, true) ?? `<code class="tex-raw">${escapeHtml(tex)}</code>`)
    return `\n\n${PH_HEAD}${atoms.length - 1}${PH_TAIL}\n\n`
  })
  text = text.replace(/\$([^$\n]+)\$/g, (_m, tex: string) => {
    atoms.push(texToHtml(tex, false) ?? `<code class="tex-raw">${escapeHtml(tex)}</code>`)
    return `${PH_HEAD}${atoms.length - 1}${PH_TAIL}`
  })

  const blocks: string[] = []
  let list: string[] = []
  let olist: string[] = []
  const flush = () => {
    if (list.length) {
      blocks.push(`<ul>${list.map((li) => `<li>${li}</li>`).join('')}</ul>`)
      list = []
    }
    if (olist.length) {
      blocks.push(`<ol>${olist.map((li) => `<li>${li}</li>`).join('')}</ol>`)
      olist = []
    }
  }

  for (const para of text.split(/\n{2,}/)) {
    const lines = para.split('\n').map((l) => l.trim()).filter(Boolean)
    if (!lines.length) continue
    // 一段里可能混着列表行和普通行，逐行归类
    let buf: string[] = []
    const emitBuf = () => {
      if (!buf.length) return
      flush()
      blocks.push(`<p>${inline(buf.join(' '))}</p>`)
      buf = []
    }
    for (const line of lines) {
      const ul = /^[-*•]\s+(.*)$/.exec(line)
      const ol = /^\d+[.)]\s+(.*)$/.exec(line)
      const atomOnly = new RegExp(`^${PH_HEAD}(\\d+)${PH_TAIL}$`).exec(line)
      if (atomOnly) {
        emitBuf()
        blocks.push(`<div class="md-block-math">${atoms[Number(atomOnly[1])]}</div>`)
      } else if (ul) {
        emitBuf()
        list.push(inline(ul[1]))
      } else if (ol) {
        emitBuf()
        olist.push(inline(ol[1]))
      } else {
        buf.push(line)
      }
    }
    emitBuf()
  }
  flush()

  return blocks
    .join('\n')
    .replace(new RegExp(`${PH_HEAD}(\\d+)${PH_TAIL}`, 'g'), (_m, i: string) => atoms[Number(i)] ?? '')
}
