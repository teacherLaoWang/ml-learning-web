/**
 * 离线演示数据层（mock）。后端没起 / 没实现某个算法时由 src/api.ts 自动切到这里。
 * 三份 JSON 在 src/fixtures/_meta/，10 份 fit 响应在 src/fixtures/{key}.json，
 * 结构与 docs/API-CONTRACT.md 完全一致；它们只服务「没有后端也能逛完整站」这一个目的。
 */
import type {
  Algorithm,
  Catalog,
  CatalogItem,
  EnvInfo,
  Family,
  FitResult,
  GlossaryPayload,
  ParamSpec,
  MetricSpec,
  Term,
  VisualSpec,
} from '../types'
import type { FitRequest } from '../api'
import catalogJson from '../fixtures/_meta/catalog.json'
import specsJson from '../fixtures/_meta/specs.json'
import lessonsJson from '../fixtures/_meta/lessons.json'

interface MetaItem extends CatalogItem {
  concept?: { story?: string; intuition?: string[]; pitfalls?: string[]; seeAlso?: string[];
    formula?: { text: string; vars?: Array<{ sym: string; zh: string }> };
    terms?: Array<{ term: string; full?: string; explain: string }> }
}

const META = catalogJson as unknown as { env: EnvInfo; families: Array<Omit<Family, 'items'> & { items: MetaItem[] }> }
const SPECS = specsJson as unknown as {
  paramSpecs: Record<string, ParamSpec[]>
  visualSpecs: Record<string, VisualSpec[]>
  metricSpecs: Record<string, MetricSpec[]>
}
const LESSONS = lessonsJson as unknown as Record<string, Omit<Algorithm, 'key' | 'family' | 'status'>>

type ConceptPack = NonNullable<MetaItem['concept']>
/** outline 概念卡片的文字（≈110KB）单独成一个懒加载 chunk，不进主包 */
let CONCEPTS: Record<string, ConceptPack> = {}
void import('../fixtures/_meta/concepts.json')
  .then((m) => { CONCEPTS = (m.default ?? m) as unknown as Record<string, ConceptPack> })
  .catch(() => { /* 拿不到就退化成只有标题的概念卡片 */ })

/** 只在浏览器里用：{key} → 懒加载 fixture（不进主包） */
const fixtureLoaders = import.meta.glob('../fixtures/*.json') as Record<string, () => Promise<{ default: FitResult }>>
const fixtureCache = new Map<string, FitResult>()

function cloneFit(key: string, req: FitRequest, source: FitResult): FitResult {
  const out: FitResult = structuredClone(source)
  out.steps = req.steps
  out.seed = req.seed
  out.params = { ...req.params }
  out.mock = true
  out.backend = 'mock'
  out.elapsedMs = 0
  out.key = key
  if (Array.isArray(out.metrics)) out.metrics = {}
  // 离线「单步/播放」：把轨迹按 step 截断，动画就能一帧一帧往前长
  for (const v of out.visuals) {
    if (v.kind === 'surface3d' && Array.isArray(v.data.path)) {
      v.data.path = v.data.path.filter((p) => p.step <= req.steps - 1)
    }
  }
  out.series = (out.series ?? []).map((s) => {
    const n = s.x.length
    const keep = Math.max(2, Math.min(n, Math.ceil((n * req.steps) / (source.steps || n))))
    return { ...s, x: s.x.slice(0, keep), y: s.y.slice(0, keep) }
  })
  out.metrics = {
    ...out.metrics,
    note: `离线演示数据：数值来自 fixtures/${key}.json，不随参数变化`,
  }
  return out
}

async function loadFixture(key: string): Promise<FitResult | null> {
  const hit = fixtureCache.get(key)
  if (hit) return hit
  const loader = Object.entries(fixtureLoaders).find(([path]) => path.endsWith(`/${key}.json`))?.[1]
  if (!loader) return null
  const mod = await loader()
  const data = (mod.default ?? mod) as FitResult
  fixtureCache.set(key, data)
  return data
}

/** 同步兜底用：fixture 还没 load 完时给一个空壳（面板会显示骨架屏） */
export function emptyFit(key: string, req: FitRequest): FitResult {
  return {
    key,
    backend: 'mock',
    steps: req.steps,
    seed: req.seed,
    params: { ...req.params },
    metrics: { note: '离线演示数据加载中…' },
    series: [],
    table: [],
    visuals: [],
    mock: true,
    declaredVisuals: (SPECS.visualSpecs[key] ?? []).map((v) => v.id),
    missingVisuals: [],
  }
}

export async function offlineFit(key: string, req: FitRequest): Promise<FitResult> {
  const fixture = await loadFixture(key)
  if (!fixture) return emptyFit(key, req)
  return cloneFit(key, req, fixture)
}

export function offlineEnv(): EnvInfo {
  return {
    python: META.env.python,
    numpy: META.env.numpy,
    torch: { available: false, version: null, device: null },
    hint: '后端未启动：现在是离线演示（mock）。启动后端：uv run uvicorn app.main:app --reload --port 8200',
  }
}

export function offlineCatalog(): Catalog {
  return {
    families: META.families.map((f) => ({
      ...f,
      items: f.items.map((it) => ({
        key: it.key,
        name: it.name,
        status: it.status,
        difficulty: it.difficulty,
        tags: it.tags,
        tagline: lessonOf(it.key)?.tagline ?? it.tagline ?? '',
      })),
    })),
    readyCount: Object.keys(SPECS.paramSpecs).length,
    totalCount: META.families.reduce((a, f) => a + f.items.length, 0),
  }
}

export function offlineSummary() {
  const cat = offlineCatalog()
  return {
    total: cat.totalCount ?? 0,
    ready: cat.readyCount ?? 0,
    families: cat.families.map((f) => ({ key: f.key, name: f.name, color: f.color })),
    incompleteLessons: [],
  }
}

function findMetaItem(key: string): { item: MetaItem; family: (typeof META.families)[number] } | null {
  for (const fam of META.families) {
    const item = fam.items.find((it) => it.key === key)
    if (item) return { item, family: fam }
  }
  return null
}

function lessonOf(key: string) {
  return LESSONS[key]
}

export function offlineReadyItems() {
  return Object.keys(SPECS.paramSpecs).map((key) => {
    const found = findMetaItem(key)
    const lesson = lessonOf(key)
    return {
      key,
      name: lesson?.name ?? found?.item.name ?? key,
      tagline: lesson?.tagline ?? found?.item.tagline ?? '',
      family: found?.family.key ?? '',
      familyName: found?.family.name ?? '',
      color: found?.family.color ?? '#2563eb',
      difficulty: found?.item.difficulty ?? 1,
      tags: found?.item.tags ?? [],
      status: (found?.item.status ?? 'ready') as 'ready' | 'outline',
    }
  })
}

export function offlineAlgorithm(key: string): Algorithm {
  const found = findMetaItem(key)
  if (!found) throw new Error(`目录里没有这个算法：${key}（可查 /api/catalog）`)
  const lesson = lessonOf(key)
  const family = found?.family
  const item = found?.item
  const concept = item?.concept ?? CONCEPTS[key]
  const isReady = !!item && item.status === 'ready'
  const base: Algorithm = {
    key,
    name: lesson?.name ?? item?.name ?? key,
    family: family?.key ?? 'other',
    familyName: family?.name ?? '其他',
    color: family?.color ?? '#2563eb',
    status: item?.status ?? 'outline',
    difficulty: item?.difficulty ?? 1,
    tags: item?.tags ?? [],
    tagline: lesson?.tagline ?? concept?.story?.slice(0, 46) ?? item?.tagline ?? '',
    story: lesson?.story ?? concept?.story ?? '',
    formula: lesson?.formula ?? concept?.formula ?? { text: '', vars: [] },
    intuition: lesson?.intuition ?? concept?.intuition ?? [],
    derivation: lesson?.derivation ?? [],
    terms: lesson?.terms ?? concept?.terms ?? [],
    pitfalls: lesson?.pitfalls ?? concept?.pitfalls ?? [],
    seeAlso: lesson?.seeAlso ?? concept?.seeAlso ?? [],
    quiz: lesson?.quiz ?? null,
    params: isReady ? (SPECS.paramSpecs[key] ?? []) : [],
    presets: lesson?.presets ?? [],
    metrics: isReady ? (SPECS.metricSpecs[key] ?? []) : [],
    visuals: isReady ? (SPECS.visualSpecs[key] ?? []) : [],
    hasSim: isReady,
  }
  return base
}

/** 与后端 loader.glossary() 同规则：按 term 去重、汇总出现在哪些算法里 */
export function offlineGlossary(): GlossaryPayload {
  const rows: Record<string, Term> = {}
  for (const key of Object.keys(LESSONS)) {
    const algo = offlineAlgorithm(key)
    for (const t of algo.terms) {
      if (!t.term) continue
      rows[t.term] = rows[t.term] ? { ...rows[t.term], keys: [...(rows[t.term].keys ?? []), key] } : { ...t, keys: [key] }
    }
  }
  const terms = Object.values(rows).sort((a, b) => a.term.localeCompare(b.term, 'zh-CN'))
  return { terms, count: terms.length }
}

/** 离线术语索引：TermTip 在后端没起时也能查到解释 */
export function offlineTermMap(): Map<string, Term> {
  const map = new Map<string, Term>()
  for (const t of offlineGlossary().terms) map.set(t.term.toLowerCase(), t)
  return map
}
