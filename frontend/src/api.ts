/**
 * 数据层：唯一的后端出口。
 *
 *  - `backendState.mode` 即 X-Backend 状态（'live' | 'mock'），请求头一并带上，方便后端日志区分
 *  - GET 自动重试一次；任何网络/5xx 失败自动退回离线数据，并把界面切到「离线演示数据（mock）」
 *  - 后端没起时整站仍可逛完：目录/教案/术语表来自 src/mock/offline，fit 来自 src/fixtures/{key}.json
 *    （契约 §3.4：fixture 与 /fit 响应结构完全一致）
 */
import { reactive } from 'vue'
import type {
  Algorithm,
  AlgorithmList,
  Catalog,
  EnvInfo,
  FitResult,
  GlossaryPayload,
  ParamSpec,
  SummaryPayload,
} from './types'
import {
  offlineAlgorithm,
  offlineCatalog,
  offlineEnv,
  offlineFit,
  offlineGlossary,
  offlineReadyItems,
  offlineSummary,
} from './mock/offline'

export type BackendMode = 'live' | 'mock'

const API_BASE = (import.meta.env?.VITE_API_BASE as string | undefined) || '/api'

export const backendState = reactive({
  mode: 'unknown' as BackendMode | 'unknown',
  /** 手动强制离线演示（顶栏开关）：方便不讲后端也能讲完整个站 */
  forceMock: false,
  probing: false,
  lastError: '',
  lastLiveAt: 0,
})

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export interface FitRequest {
  params: Record<string, number>
  seed: number
  steps: number
}

function markLive() {
  backendState.mode = 'live'
  backendState.lastLiveAt = Date.now()
  backendState.lastError = ''
}

function markMock(err: unknown) {
  if (backendState.mode === 'live') backendState.lastError = ''
  backendState.mode = 'mock'
  backendState.lastError = err instanceof Error ? err.message : String(err)
}

interface RequestOpts {
  method?: 'GET' | 'POST'
  body?: unknown
  timeoutMs?: number
  retries?: number
  signal?: AbortSignal
}

async function request<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const { method = 'GET', body, timeoutMs = 8000, retries = method === 'GET' ? 1 : 0, signal } = opts
  let lastErr: unknown = null

  for (let attempt = 0; attempt <= retries; attempt++) {
    if (signal?.aborted) throw new DOMException('已取消', 'AbortError')
    const ctrl = new AbortController()
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      ctrl.abort()
    }, timeoutMs)
    const onAbort = () => ctrl.abort()
    signal?.addEventListener('abort', onAbort)
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method,
        headers: {
          Accept: 'application/json',
          'X-Backend': backendState.forceMock ? 'mock' : 'live',
          ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      })
      if (!res.ok) {
        const payload = await res.json().catch(() => null)
        const msg = typeof payload?.detail === 'string' && payload.detail ? payload.detail : `HTTP ${res.status}`
        const err = new ApiError(msg, res.status)
        if (res.status < 500) throw err // 业务错误（404 无此算法 / 400 参数非法）：不重试、不假装成功
        lastErr = err
        continue
      }
      const json = (await res.json()) as T
      markLive()
      return json
    } catch (e) {
      if (e instanceof ApiError && e.status < 500) throw e
      if (signal?.aborted && !timedOut) throw e instanceof DOMException ? e : new DOMException('已取消', 'AbortError')
      lastErr = timedOut ? new Error(`请求超时（${(timeoutMs / 1000).toFixed(0)}s）`) : e
      if (attempt < retries) await new Promise((r) => setTimeout(r, 240 * (attempt + 1)))
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', onAbort)
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error('请求失败')
}

/**
 * 有离线兜底就兜底，没有就抛错。
 * 注意：调用方抛错时要看到中文原因，所以 4xx（例如「暂无仿真实现」）不静默降级。
 */
async function withFallback<T>(path: string, opts: RequestOpts, offline: () => T): Promise<T> {
  if (backendState.forceMock) {
    backendState.mode = 'mock'
    return offline()
  }
  try {
    return await request<T>(path, opts)
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    // 400 = 参数非法：必须把中文原因抛给使用者，不能拿假数据糊过去。
    // 404（静态服务器上没有 /api）与 5xx（该算法内核还没写）→ 退回离线演示，界面会亮出 mock 标注。
    if (e instanceof ApiError && e.status === 400) throw e
    markMock(e)
    return offline()
  }
}

export async function getEnv(signal?: AbortSignal): Promise<EnvInfo> {
  return withFallback('/env', { timeoutMs: 5000, signal }, () => {
    markMock(new Error('后端未启动'))
    return offlineEnv()
  })
}

export async function getCatalog(signal?: AbortSignal): Promise<Catalog> {
  return withFallback('/catalog', { timeoutMs: 9000, signal }, () => {
    markMock(new Error('后端未启动'))
    return offlineCatalog()
  })
}

export async function getAlgorithms(signal?: AbortSignal): Promise<AlgorithmList> {
  return withFallback('/algorithms', { timeoutMs: 9000, signal }, () => {
    markMock(new Error('后端未启动'))
    return { items: offlineReadyItems() }
  })
}

export async function getAlgorithm(key: string, signal?: AbortSignal): Promise<Algorithm> {
  return withFallback(`/algorithms/${encodeURIComponent(key)}`, { timeoutMs: 9000, signal }, () => {
    markMock(new Error('后端未启动'))
    return offlineAlgorithm(key)
  })
}

export async function getGlossary(signal?: AbortSignal): Promise<GlossaryPayload> {
  return withFallback('/glossary', { timeoutMs: 9000, signal }, () => {
    markMock(new Error('后端未启动'))
    return offlineGlossary()
  })
}

export async function getSummary(signal?: AbortSignal): Promise<SummaryPayload> {
  return withFallback('/summary', { timeoutMs: 6000, signal }, () => {
    markMock(new Error('后端未启动'))
    return offlineSummary()
  })
}

/** 真跑训练；后端不在时用 fixture，并按 steps 截断以支持离线「单步/播放」 */
export async function fit(key: string, req: FitRequest, signal?: AbortSignal): Promise<FitResult> {
  return withFallback(
    `/algorithms/${encodeURIComponent(key)}/fit`,
    { method: 'POST', body: req, timeoutMs: 30000, signal },
    () => {
      markMock(new Error('后端未启动'))
      return offlineFit(key, req)
    },
  )
}

/** 单步推进（后端 /step = 重算到第 steps 步，返回 resumed:true） */
export async function step(key: string, req: FitRequest, signal?: AbortSignal): Promise<FitResult> {
  return withFallback(
    `/algorithms/${encodeURIComponent(key)}/step`,
    { method: 'POST', body: req, timeoutMs: 30000, signal },
    () => {
      markMock(new Error('后端未启动'))
      return { ...offlineFit(key, req), resumed: true }
    },
  )
}

/* ------------------------------------------------------ 参数面板的小工具 */

/** 契约 §1：请求里未给的参数用 `params[].default` */
export function defaultsFrom(specs: ParamSpec[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const s of specs) out[s.id] = s.default
  return out
}

export function clampParam(spec: ParamSpec, value: number): number {
  const step = spec.step > 0 ? spec.step : 1
  const raw = Number.isFinite(value) ? value : spec.default
  const snapped = Math.round((raw - spec.min) / step) * step + spec.min
  return Math.max(spec.min, Math.min(spec.max, Number(snapped.toFixed(6))))
}
