<script setup lang="ts">
/**
 * 算法详情页（/algo/:key）：左教案 + 右仿真台。
 *
 * 所有控件都由后端目录驱动（不做算法专属硬编码）：
 *   params   ← catalog.PARAM_SPECS   → ParamsPanel
 *   visuals  ← catalog.VISUAL_SPEC   → VisualStage（按 kind 分派组件）
 *   metrics  ← catalog.METRIC_SPEC   → MetricsStrip
 * status = outline 的条目只渲染教案（概念卡片），右侧不出现仿真台。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import VisualStage from '../components/VisualStage.vue'
import ParamsPanel from '../components/ParamsPanel.vue'
import StepPlayer from '../components/StepPlayer.vue'
import MetricsStrip from '../components/MetricsStrip.vue'
import FormulaCard from '../components/FormulaCard.vue'
import TableCard from '../components/TableCard.vue'
import LessonText from '../components/LessonText.vue'
import TermTip from '../components/TermTip.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import Chart2D from '../components/Chart2D.vue'
import { backendState, defaultsFrom, fit, getAlgorithm, getCatalog, step } from '../api'
import type { Algorithm, FitResult, Line2DVisual, SeriesRow } from '../types'
import { clamp, debounce } from '../utils/format'

const route = useRoute()
const key = computed(() => String(route.params.key ?? ''))

const algo = ref<Algorithm | null>(null)
const algoLoading = ref(true)
const loadError = ref('')

const params = ref<Record<string, number>>({})
const seed = ref(7)
const steps = ref(150)

const result = ref<FitResult | null>(null)
const busy = ref(false)
const fitError = ref('')
const trained = ref(0)

const frame = ref(0)
const playing = ref(false)
const speed = ref(1)

const hasSim = computed(() => !!algo.value?.hasSim && (algo.value?.params?.length ?? 0) > 0)
const maxFrame = computed(() => Math.max(0, Math.min(steps.value, trained.value || steps.value) - 1))
const specsForStage = computed(() => algo.value?.visuals ?? [])
const visualData = computed(() => result.value?.visuals ?? [])

/** 取有限值的真实范围并加 8% 余量；退化（全相等/空）时给一个可用的窗口 */
function paddedExtent(vals: number[] | undefined, fallback: [number, number] = [0, 1]): [number, number] {
  const arr = (vals ?? []).filter((v) => Number.isFinite(v))
  if (!arr.length) return fallback
  let lo = Math.min(...arr)
  let hi = Math.max(...arr)
  if (hi - lo < 1e-9) {
    const pad = Math.max(Math.abs(hi) * 0.1, 1e-3)
    return [lo - pad, hi + pad]
  }
  const pad = (hi - lo) * 0.08
  lo -= pad
  hi += pad
  return [lo, hi]
}

/** series[] 复用同一个折线组件：合成 line2d 负载 */
const seriesVisuals = computed<Line2DVisual[]>(() =>
  (result.value?.series ?? []).map((s: SeriesRow) => {
    // 用数据自身范围（含 8% 余量），不要强行含 0 和 1：
    // 否则验证误差 0.15~0.17 这种窄区间会被压成贴边直线，图就白画了
    const [xmin, xmax] = paddedExtent(s.x)
    const [ymin, ymax] = paddedExtent(s.y)
    return {
      id: `series-${s.id}`,
      kind: 'line2d',
      title: `${s.label}（序列）`,
      hint: '随播放头一起生长；灰色虚线是后端返回的原始采样',
      data: {
        curves: [{ id: s.id, label: s.label, x: s.x, y: s.y, dash: false, color: '#2563eb' }],
        axes: {
          x: { label: s.xLabel ?? 'step', min: xmin, max: xmax },
          y: { label: s.yLabel ?? '值', min: ymin, max: ymax },
        },
      },
    }
  }),
)

let ctrl: AbortController | null = null

async function run(): Promise<void> {
  if (!hasSim.value) return
  ctrl?.abort()
  const my = new AbortController()
  ctrl = my
  busy.value = true
  fitError.value = ''
  try {
    const r = await fit(key.value, { params: params.value, seed: seed.value, steps: steps.value }, my.signal)
    if (my.signal.aborted) return
    result.value = r
    trained.value = r.steps || steps.value
    frame.value = clamp(frame.value, 0, Math.max(0, Math.min(steps.value, trained.value) - 1))
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    fitError.value = e instanceof Error ? e.message : String(e)
    result.value = null
  } finally {
    if (ctrl === my) busy.value = false
  }
}

/** 「单步」：先在已训练轨迹内走一格；走到尽头再调 /step 续算 10 步 */
async function stepOnce(): Promise<void> {
  if (!hasSim.value) return
  playing.value = false
  if (frame.value < maxFrame.value) {
    frame.value += 1
    return
  }
  if (trained.value >= 400 || busy.value) return
  ctrl?.abort()
  const my = new AbortController()
  ctrl = my
  busy.value = true
  fitError.value = ''
  try {
    const target = Math.min(400, trained.value + 10)
    const r = await step(key.value, { params: params.value, seed: seed.value, steps: target }, my.signal)
    if (my.signal.aborted) return
    result.value = r
    trained.value = r.steps || target
    frame.value = clamp(frame.value + 1, 0, Math.max(0, trained.value - 1))
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    fitError.value = e instanceof Error ? e.message : String(e)
    result.value = null
  } finally {
    if (ctrl === my) busy.value = false
  }
}

function resetPlayback() {
  playing.value = false
  frame.value = 0
}

function resetAll() {
  if (algo.value) params.value = defaultsFrom(algo.value.params)
  seed.value = 7
  steps.value = 150
  resetPlayback()
  void run()
}

async function loadLesson(): Promise<void> {
  algoLoading.value = true
  loadError.value = ''
  result.value = null
  trained.value = 0
  frame.value = 0
  playing.value = false
  try {
    const k = key.value
    const a = await getAlgorithm(k)
    if (key.value !== k) return // 连点两个算法时，旧响应不能覆盖新页
    algo.value = a
    params.value = defaultsFrom(a.params ?? [])
    await run()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
    algo.value = null
  } finally {
    algoLoading.value = false
  }
}

const scheduleRun = debounce(() => {
  resetPlayback()
  void run()
}, 600)

watch(params, () => {
  if (hasSim.value) scheduleRun()
})
watch(steps, () => {
  if (hasSim.value) scheduleRun()
})
watch(seed, () => {
  if (hasSim.value) scheduleRun()
})
watch(key, () => void loadLesson())

/* 键盘：空格播放/暂停，←/→ 单步，R 重跑 */
function onKey(ev: KeyboardEvent) {
  const target = ev.target as HTMLElement | null
  if (target && /input|textarea|select/i.test(target.tagName)) return
  // Cmd/Ctrl+R 是「刷新页面」，不该被当成重跑；Alt 同理
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return
  if (!hasSim.value) return
  if (ev.code === 'Space') {
    // 焦点在按钮上时空格属于该按钮（例如「应用并重跑」），不能同时再触发播放
    if (target && /button/i.test(target.tagName)) return
    ev.preventDefault()
    playing.value = !playing.value
  } else if (ev.key === 'ArrowRight') {
    ev.preventDefault()
    void stepOnce()
  } else if (ev.key === 'ArrowLeft') {
    ev.preventDefault()
    playing.value = false
    frame.value = clamp(frame.value - 1, 0, maxFrame.value)
  } else if (ev.key.toLowerCase() === 'r') {
    void run()
  }
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  void loadLesson()
  if (catalogReady.value === null) {
    getCatalog()
      .then((c) => {
        catalogReady.value = c.families.flatMap((f) => f.items.filter((i) => i.status === 'ready').map((i) => i.key))
      })
      .catch(() => {
        catalogReady.value = []
      })
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  ctrl?.abort()
})

function scrollToSection(id: string): void {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/* ---------------------------------------------------------- 教案小工具 */

const nav = computed(() => {
  const a = algo.value
  if (!a) return []
  const out: Array<{ id: string; label: string }> = [{ id: 'story', label: '故事' }]
  if (a.formula?.text) out.push({ id: 'formula', label: '公式' })
  if (a.intuition?.length) out.push({ id: 'intuition', label: '直觉' })
  if (a.derivation?.length) out.push({ id: 'derivation', label: '推导' })
  if (a.pitfalls?.length) out.push({ id: 'pitfalls', label: '常见坑' })
  if (a.quiz) out.push({ id: 'quiz', label: '自测' })
  return out
})

const catalogReady = ref<string[] | null>(null)

const picked = ref<number | null>(null)
watch(key, () => (picked.value = null))
const quizRight = computed(() => (picked.value === null ? null : picked.value === (algo.value?.quiz?.answer ?? -1)))

const siblings = computed(() => (algo.value ? [algo.value.key, ...(algo.value.seeAlso ?? [])] : []))
const missing = computed(() => algo.value?.missingText ?? [])
</script>

<template>
  <div v-if="algoLoading" class="loading">
    <SkeletonBlock :lines="6" height="150px" label="正在读取教案与首次训练结果…" />
    <SkeletonBlock :lines="2" height="380px" label="3D 面板准备中…" />
  </div>

  <div v-else-if="loadError" class="card err-card">
    <div class="err-banner">{{ loadError }}</div>
    <RouterLink class="btn btn-sm" to="/catalog">返回目录</RouterLink>
  </div>

  <div v-else-if="algo" class="detail">
    <header class="card top">
      <div class="row-between">
        <div>
          <div class="row crumb tiny">
            <RouterLink to="/catalog">全景目录</RouterLink>
            <span>/</span>
            <RouterLink :to="`/catalog#${algo.family}`">{{ algo.familyName }}</RouterLink>
            <span class="chip" :class="algo.status === 'ready' ? 'chip-ok' : 'chip-warn'">
              {{ algo.status === 'ready' ? '已精做 · 有仿真台' : '概念卡片 · 无仿真台' }}
            </span>
          </div>
          <h1>{{ algo.name }} <span class="chip tiny mono">{{ algo.key }}</span></h1>
          <p class="muted lede">{{ algo.tagline }}</p>
          <div class="row">
            <span v-for="t in algo.tags" :key="t" class="chip tiny">{{ t }}</span>
            <span class="tiny mono lvl">难度 {{ '●'.repeat(algo.difficulty) }}{{ '○'.repeat(Math.max(0, 5 - algo.difficulty)) }}</span>
          </div>
        </div>
        <nav class="toc">
          <!-- 路由是 hash 模式，用 #id 锚点会把整条路由换掉；这里改成脚本滚动 -->
          <button v-for="n in nav" :key="n.id" type="button" class="tiny toc-link" @click="scrollToSection(n.id)">
            {{ n.label }}
          </button>
        </nav>
      </div>
      <p v-if="backendState.mode === 'mock' && hasSim" class="tiny mockline">
        本页仿真数据来自 <code>src/fixtures/{{ algo.key }}.json</code>（离线演示）：轨迹、点云、动画都在真的跑，
        但数值不随参数变化。启动后端 <code>uv run uvicorn app.main:app --reload --port 8200</code> 后即为真跑。
      </p>
    </header>

    <div class="cols">
      <!-- ================================================== 左：教案 -->
      <div class="lesson">
        <section id="story" class="card sec">
          <h2>故事</h2>
          <p v-if="algo.story"><LessonText :text="algo.story" /></p>
          <p v-else class="tiny muted">（这篇教案的正文还没写：后端 app/content/lessons/{{ algo.key }}.py 缺 story）</p>
        </section>

        <div id="formula" class="sec">
          <FormulaCard :formula="algo.formula" />
        </div>

        <section v-if="algo.intuition?.length" id="intuition" class="card sec">
          <h2>直觉</h2>
          <p v-for="(p, i) in algo.intuition" :key="i"><LessonText :text="p" /></p>
        </section>

        <section v-if="algo.derivation?.length" id="derivation" class="card sec">
          <h2>推导分步</h2>
          <ol class="steps">
            <li v-for="(d, i) in algo.derivation" :key="i">
              <b>{{ d.title || `第 ${i + 1} 步` }}</b>
              <p class="small"><LessonText :text="d.body" /></p>
              <p v-if="d.formula" class="mono f-line">{{ d.formula }}</p>
            </li>
          </ol>
        </section>

        <section v-if="algo.pitfalls?.length" id="pitfalls" class="card sec">
          <h2>常见坑</h2>
          <ul class="pits">
            <li v-for="(p, i) in algo.pitfalls" :key="i"><LessonText :text="p" /></li>
          </ul>
        </section>

        <section v-if="algo.quiz" id="quiz" class="card sec">
          <h2>自测题</h2>
          <p><LessonText :text="algo.quiz.q" /></p>
          <div class="quiz">
            <button
              v-for="(opt, i) in algo.quiz.options"
              :key="i"
              class="q-opt"
              :class="{ right: picked !== null && i === algo.quiz.answer, wrong: picked === i && i !== algo.quiz.answer }"
              @click="picked = i"
            >
              <span class="mono tiny">{{ String.fromCharCode(65 + i) }}</span>{{ opt }}
            </button>
          </div>
          <p v-if="picked !== null" class="why" :class="{ ok: quizRight }">
            {{ quizRight ? '答对了。' : '再想想。' }}<LessonText :text="algo.quiz.why ?? ''" />
          </p>
        </section>

        <section class="card sec">
          <h2>相关算法</h2>
          <div class="row">
            <RouterLink v-for="k in siblings" :key="k" class="chip" :to="`/algo/${k}`">{{ k }}</RouterLink>
          </div>
          <details v-if="algo.terms?.length" class="fold sec-fold">
            <summary>术语表（{{ algo.terms.length }} 条，本页关键词）</summary>
            <div class="fold-body terms">
              <div v-for="t in algo.terms" :key="t.term" class="term-row">
                <TermTip :term="t.term" :full="t.full" :explain="t.explain"><b>{{ t.term }}</b></TermTip>
                <span class="tiny muted">{{ t.explain }}</span>
              </div>
            </div>
          </details>
          <p v-if="missing.length" class="tiny muted">
            内容体检：这篇还缺 {{ missing.join('、') }}（后端 loader 的 REQUIRED_TEXT 检查）。
          </p>
        </section>
      </div>

      <!-- ================================================== 右：仿真台 -->
      <div class="sim">
        <template v-if="hasSim">
          <ParamsPanel
            v-model="params"
            v-model:seed="seed"
            v-model:steps="steps"
            :specs="algo.params"
            :presets="algo.presets"
            :busy="busy"
            @run="run"
            @reset="resetAll"
          />

          <StepPlayer
            v-model:frame="frame"
            v-model:playing="playing"
            v-model:speed="speed"
            :max-frame="maxFrame"
            :busy="busy"
            :fetched-steps="trained"
            @step="stepOnce"
            @reset="resetPlayback"
            @run="run"
          />

          <MetricsStrip
            :specs="algo.metrics"
            :metrics="result?.metrics ?? {}"
            :backend="result?.backend"
            :elapsed-ms="result?.elapsedMs"
            :steps="result?.steps ?? 0"
            :seed="result?.seed ?? seed"
            :mock="!!result?.mock"
            :resumed="!!result?.resumed"
          />

          <div v-if="fitError" class="err-banner">{{ fitError }}</div>
          <p v-if="result?.missingVisuals?.length" class="tiny muted">
            后端声明缺少的 visual：<code>{{ result.missingVisuals.join('、') }}</code>
          </p>

          <VisualStage
            :specs="specsForStage"
            :visuals="visualData"
            :frame="frame"
            :max-frame="maxFrame"
            :loading="busy && !result"
            :algo-key="algo.key"
          />

          <section v-if="seriesVisuals.length" class="card series">
            <div class="card-head">
              <h3>训练序列（/fit 的 series[]）</h3>
              <span class="chip tiny mono">{{ seriesVisuals.length }} 条</span>
            </div>
            <div class="series-grid">
              <div v-for="s in seriesVisuals" :key="s.id" class="series-cell">
                <Chart2D :visual="s" :progress="maxFrame ? frame / maxFrame : 1" :active="true" />
              </div>
            </div>
          </section>

          <TableCard v-for="tb in result?.table ?? []" :key="tb.id" :table="tb" />
        </template>

        <section v-else class="card no-sim">
          <div class="card-head">
            <h2>这是概念卡片</h2>
            <span class="chip chip-warn">status = outline</span>
          </div>
          <p class="small muted">
            目录里标为 outline 的条目只提供只读讲解（左栏），没有参数面板与 3D 仿真台。
            想动手，可以从同一个大类的已精做算法开始：
          </p>
          <div class="row">
            <RouterLink
              v-for="s in (catalogReady ?? []).filter((x: string) => x !== algo?.key).slice(0, 8)"
              :key="s"
              class="btn btn-sm"
              :to="`/algo/${s}`"
            >
              {{ s }}
            </RouterLink>
            <RouterLink class="btn btn-sm" to="/catalog">看全部目录</RouterLink>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>


<style scoped>
.loading {
  display: grid;
  gap: 12px;
}
.err-card {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.detail {
  display: grid;
  gap: 12px;
}
.top h1 {
  margin: 2px 0 4px;
  font-size: 24px;
}
.crumb {
  gap: 5px;
  color: var(--muted);
}
.lede {
  margin: 0 0 6px;
  max-width: 78ch;
}
.lvl {
  color: var(--muted);
  letter-spacing: 1px;
}
.toc {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-content: flex-start;
}
.toc a,
.toc .toc-link {
  padding: 3px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--panel-2);
  color: var(--ink-2);
  font-weight: 650;
  cursor: pointer;
}
.toc a:hover,
.toc .toc-link:hover {
  text-decoration: none;
  border-color: var(--accent);
  color: var(--accent);
}
.mockline {
  margin: 10px 0 0;
  color: var(--mock);
  background: #fef2f2;
  border: 1px dashed #f3c6c6;
  border-radius: 10px;
  padding: 6px 9px;
}
.cols {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.32fr);
  gap: 14px;
  align-items: start;
}
.lesson,
.sim {
  display: grid;
  gap: 12px;
}
.sec h2 {
  font-size: 16px;
  margin: 0 0 6px;
}
.sec {
  scroll-margin-top: 70px;
}
.steps {
  margin: 0;
  padding-left: 22px;
  display: grid;
  gap: 10px;
}
.steps b {
  font-size: 13.5px;
}
.steps p {
  margin: 2px 0;
  color: var(--ink-2);
}
.f-line {
  margin: 2px 0 0;
  background: var(--panel-2);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 5px 8px;
  font-size: 12.5px;
  overflow-x: auto;
}
.pits {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 7px;
}
.pits li {
  color: var(--ink-2);
  font-size: 13.5px;
}
.quiz {
  display: grid;
  gap: 6px;
  margin-top: 6px;
}
.q-opt {
  font: inherit;
  font-size: 13.5px;
  text-align: left;
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  cursor: pointer;
}
.q-opt:hover {
  border-color: var(--accent);
}
.q-opt .mono {
  color: var(--muted);
  font-weight: 700;
}
.q-opt.right {
  border-color: #16a34a;
  background: #ecfdf3;
}
.q-opt.wrong {
  border-color: #dc2626;
  background: #fef2f2;
}
.why {
  font-size: 13px;
  color: var(--warn);
  background: #fdf3e4;
  border-radius: 9px;
  padding: 6px 9px;
}
.why.ok {
  color: var(--ok);
  background: #e9f8f3;
}
.sec-fold {
  margin-top: 10px;
}
.terms {
  display: grid;
  gap: 7px;
}
.term-row {
  display: grid;
  gap: 1px;
}
.series {
  display: grid;
  gap: 8px;
}
.series h3 {
  margin: 0;
  font-size: 14px;
}
.series-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}
.series-cell {
  border: 1px solid var(--line-2);
  border-radius: 10px;
}
.no-sim h2 {
  margin: 0;
  font-size: 16px;
}
@media (max-width: 1080px) {
  .cols {
    grid-template-columns: 1fr;
  }
}
</style>
