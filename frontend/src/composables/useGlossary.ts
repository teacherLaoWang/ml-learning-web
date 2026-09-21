/**
 * 术语表全局 store：TermTip 与正文自动标注都从这里查。
 * 后端没起时用 offlineTermMap() 的离线术语兜底（保证整站可逛）。
 */
import { computed, reactive } from 'vue'
import { getGlossary } from '../api'
import { offlineGlossary } from '../mock/offline'
import type { Term } from '../types'

interface GlossaryState {
  terms: Term[]
  map: Map<string, Term>
  loaded: boolean
  loading: boolean
  error: string
  pattern: RegExp | null
}

const state = reactive<GlossaryState>({
  terms: [],
  map: new Map(),
  loaded: false,
  loading: false,
  error: '',
  pattern: null,
})

export function normalizeTerm(s: string): string {
  return s.toLowerCase().replace(/[\s\u3000]+/g, '').trim()
}

function rebuild() {
  const map = new Map<string, Term>()
  for (const t of state.terms) {
    map.set(normalizeTerm(t.term), t)
    if (t.full) map.set(normalizeTerm(t.full), t)
  }
  state.map = map
  const keys = state.terms
    .flatMap((t) => [t.term, t.full ?? ''])
    .filter((k) => k.length >= 2)
    .sort((a, b) => b.length - a.length)
  state.pattern = keys.length
    ? new RegExp(`(${keys.map(escapeRe).join('|')})`, 'g')
    : null
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

let pending: Promise<void> | null = null

export function loadGlossary(force = false): Promise<void> {
  if (state.loaded && !force) return Promise.resolve()
  if (pending) return pending
  state.loading = true
  pending = (async () => {
    try {
      const payload = await getGlossary()
      state.terms = payload.terms ?? []
    } catch (e) {
      state.error = e instanceof Error ? e.message : String(e)
      state.terms = offlineGlossary().terms
    } finally {
      state.loading = false
      state.loaded = true
      pending = null
      rebuild()
    }
  })()
  return pending
}

export function useGlossary() {
  return {
    terms: computed(() => state.terms),
    pattern: computed(() => state.pattern),
    loading: computed(() => state.loading),
    loaded: computed(() => state.loaded),
    error: computed(() => state.error),
    count: computed(() => state.terms.length),
    find: (text: string): Term | undefined => state.map.get(normalizeTerm(text)),
    load: loadGlossary,
  }
}

export function lookupTerm(text: string): Term | undefined {
  return state.map.get(normalizeTerm(text))
}
