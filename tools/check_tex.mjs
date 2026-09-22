#!/usr/bin/env node
/**
 * 用真正的 KaTeX 把站内每条公式都排一遍版，抓出解析不了的 LaTeX。
 *
 * 前端渲染时 throwOnError=false（坏公式只标红，不能打断页面），
 * 所以「写坏了 LaTeX」在运行时是静默的 —— 这个脚本用严格模式补上这一关。
 *
 * 用法： cd frontend && node ../tools/check_tex.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, join, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const FRONTEND = resolve(here, '..', 'frontend')
// katex 装在 frontend 下，脚本在 tools/ 里，ESM 不会跨目录找 → 按绝对路径动态导入
const { default: katex } = await import(
  pathToFileURL(join(FRONTEND, 'node_modules', 'katex', 'dist', 'katex.mjs')).href
)

const FILES = ['_meta/lessons.json', '_meta/concepts.json']

/** 收集 {path, tex, display} */
function collect(node, path, out) {
  if (Array.isArray(node)) {
    node.forEach((v, i) => collect(v, `${path}[${i}]`, out))
    return
  }
  if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node)) collect(v, path ? `${path}.${k}` : k, out)
    return
  }
  if (typeof node !== 'string') return
  if (path.endsWith('.latex')) out.push({ path, tex: node, display: !path.includes('.vars') })
  if (path.endsWith('.text') || path.endsWith('.body') || path.endsWith('.explain') || path.endsWith('.zh')) {
    for (const m of node.matchAll(/\$\$([^$]+)\$\$|\$([^$\n]+)\$/g)) {
      out.push({ path, tex: m[1] ?? m[2], display: Boolean(m[1]) })
    }
  }
}

const seen = new Set()
const items = []
for (const rel of FILES) {
  let json
  try {
    json = JSON.parse(readFileSync(join(FRONTEND, 'src', 'fixtures', rel), 'utf8'))
  } catch (e) {
    console.error(`读不了 ${rel}：${e.message}（先跑 uv run python -m tools.make_fixtures）`)
    process.exit(1)
  }
  collect(json, '', items)
}

let bad = 0
const deduped = items.filter((it) => {
  const key = `${it.display}${it.tex}`
  if (seen.has(key)) return false
  seen.add(key)
  return true
})
for (const it of deduped) {
  if (!it.tex.trim()) continue
  try {
    katex.renderToString(it.tex, { displayMode: it.display, throwOnError: true, strict: 'error' })
  } catch (e) {
    bad++
    const msg = String(e.message).split('\n')[0].slice(0, 140)
    console.log(`✗ ${it.path}\n    ${it.tex.slice(0, 100)}\n    ${msg}`)
  }
}
console.log(`\n检查 ${deduped.length} 条唯一公式（共 ${items.length} 处引用），${bad ? `✗ ${bad} 条排不了版` : '全部可排版 ✓'}`)
process.exit(bad ? 1 : 0)
