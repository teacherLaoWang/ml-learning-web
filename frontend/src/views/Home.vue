<script setup lang="ts">
/**
 * 首页：站点定位 + 环境状态卡（/api/env）+ 六大类入口 + ready 算法卡片网格。
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import TermTip from '../components/TermTip.vue'
import { getAlgorithms, getCatalog, getEnv, backendState } from '../api'
import type { AlgorithmList, Catalog, EnvInfo } from '../types'
import { fmtInt } from '../utils/format'
import { useDocumentVisible } from '../composables/useVisibility'

const env = ref<EnvInfo | null>(null)
const catalog = ref<Catalog | null>(null)
const ready = ref<AlgorithmList['items']>([])
const loading = ref(true)
const error = ref('')
const visible = useDocumentVisible()

const stats = computed(() => ({
  total: catalog.value?.totalCount ?? catalog.value?.families.reduce((a, f) => a + f.items.length, 0) ?? 0,
  ready: catalog.value?.readyCount ?? ready.value.length,
  families: catalog.value?.families.length ?? 0,
}))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [e, c, a] = await Promise.all([getEnv(), getCatalog(), getAlgorithms()])
    env.value = e
    catalog.value = c
    ready.value = a.items
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)
const highlights = [
  { icon: '◐', title: '真的能转', text: '每个仿真台都是 three.js 实时场景：拖动旋转、双指缩放、俯视侧视切换，标签永远压在线和点之上。' },
  { icon: '▶', title: '真的能动', text: '轨迹插值、卷积窗口逐格滑动、点云向质心收缩、等高线相位流动 —— 由 rAF + 时间累加器驱动，可单步可回放。' },
  { icon: '◫', title: '真的能算', text: '后端 FastAPI + NumPy（装了 PyTorch 自动升级内核）真跑训练，前端只按契约消费 JSON。' },
]
</script>

<template>
  <div class="home">
    <section class="hero card">
      <div class="hero-text">
        <p class="eyebrow tiny">交互式机器学习教室 · 3D 仿真 · 中文讲解</p>
        <h1>把「损失曲面」变成可以拿在手里转的东西</h1>
        <p class="lede">
          41 个算法条目、{{ stats.ready }} 个精做为可交互仿真台。每个页面左边是教案（故事 → 公式与变量释义 → 直觉 →
          分步推导 → 常见坑 → 自测题），右边是真跑出来的 3D/2D 结果：拖一下时间轴，看梯度怎么走过谷底、卷积窗口如何逐格滑动。
        </p>
        <div class="row">
          <RouterLink class="btn btn-primary" to="/catalog">打开全景目录</RouterLink>
          <RouterLink class="btn" to="/glossary">术语速查</RouterLink>
          <RouterLink v-if="ready.length" class="btn" :to="`/algo/${ready[0].key}`">直接看第一个仿真台</RouterLink>
        </div>
      </div>
      <ul class="hl">
        <li v-for="h in highlights" :key="h.title">
          <span class="hl-icon">{{ h.icon }}</span>
          <div>
            <b>{{ h.title }}</b>
            <p class="tiny muted">{{ h.text }}</p>
          </div>
        </li>
      </ul>
    </section>

    <section class="grid two status-grid">
      <div class="card">
        <div class="card-head">
          <h3>运行环境</h3>
          <span class="chip" :class="backendState.mode === 'live' ? 'chip-ok' : 'chip-mock'">
            {{ backendState.mode === 'live' ? '实时后端' : '离线演示（mock）' }}
          </span>
        </div>
        <SkeletonBlock v-if="loading" :lines="2" height="42px" label="正在读取 /api/env…" />
        <div v-else-if="env" class="env">
          <div class="env-row">
            <span class="tiny muted">Python</span><b class="mono">{{ env.python }}</b>
          </div>
          <div class="env-row">
            <span class="tiny muted"><TermTip term="NumPy" explain="数值计算内核；所有演示都能只靠它跑。">NumPy</TermTip></span>
            <b class="mono">{{ env.numpy ?? '未安装' }}</b>
          </div>
          <div class="env-row">
            <span class="tiny muted"><TermTip term="PyTorch" explain="可选自动微分内核：装了之后训练走 torch，没装自动退回 NumPy 实现。">PyTorch</TermTip></span>
            <b v-if="env.torch?.available" class="chip chip-ok mono">{{ env.torch.version }} · {{ env.torch.device }}</b>
            <b v-else class="chip chip-warn">未安装</b>
          </div>
          <p v-if="env.hint" class="hint">
            {{ env.hint }}
            <code>uv sync --extra ml</code>
          </p>
          <p v-else class="hint tiny muted">内核就绪：训练页面上的数字都是这台机器现算出来的。</p>
        </div>
        <div v-else class="err-banner">{{ error || '读不到环境信息' }}</div>
      </div>

      <div class="card">
        <div class="card-head">
          <h3>站点进度</h3>
          <span class="chip tiny mono">{{ visible ? '渲染中' : '已暂停渲染' }}</span>
        </div>
        <div class="stats">
          <div><b class="mono">{{ fmtInt(stats.total) }}</b><span class="tiny muted">条目总数</span></div>
          <div><b class="mono">{{ fmtInt(stats.ready) }}</b><span class="tiny muted">已精做（有 3D 仿真）</span></div>
          <div><b class="mono">{{ fmtInt(stats.families) }}</b><span class="tiny muted">大类</span></div>
        </div>
        <div v-if="catalog" class="families">
          <RouterLink v-for="f in catalog.families" :key="f.key" class="fam" :to="`/catalog#${f.key}`">
            <i :style="{ background: f.color }" />
            <span>{{ f.name }}</span>
            <em class="tiny mono">{{ f.items.length }}</em>
          </RouterLink>
        </div>
        <p class="tiny muted progress-note">
          status = outline 的条目是「概念卡片」：只读教案，没有仿真台；点进目录可展开看讲解。
        </p>
      </div>
    </section>

    <h2 class="section-title">可直接开跑的算法（ready）</h2>
    <SkeletonBlock v-if="loading" :lines="4" height="86px" label="正在读取 /api/catalog 与 /api/algorithms…" />
    <div v-else class="algo-grid">
      <RouterLink v-for="a in ready" :key="a.key" class="algo" :to="`/algo/${a.key}`" :style="{ borderColor: `${a.color}33` }">
        <div class="algo-top">
          <b>{{ a.name }}</b>
          <span class="chip tiny mono">{{ a.key }}</span>
        </div>
        <p class="tiny muted tagline">{{ a.tagline || '（教案文字待后端补充）' }}</p>
        <div class="row tags">
          <span v-for="t in a.tags.slice(0, 3)" :key="t" class="chip tiny">{{ t }}</span>
        </div>
        <div class="algo-foot tiny">
          <span class="dots">{{ '●'.repeat(a.difficulty) }}{{ '○'.repeat(Math.max(0, 5 - a.difficulty)) }}</span>
          <span>{{ a.familyName }}</span>
        </div>
      </RouterLink>
    </div>
  </div>
</template>

<style scoped>
.home {
  display: grid;
  gap: 6px;
}
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(260px, 1fr);
  gap: 18px;
  padding: 20px 22px;
  background: linear-gradient(180deg, #fff 0%, #f7f9ff 100%);
}
.eyebrow {
  margin: 0 0 4px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 700;
}
.hero h1 {
  margin: 0 0 8px;
  font-size: 28px;
}
.lede {
  color: var(--ink-2);
  max-width: 62ch;
  margin: 0 0 14px;
}
.hl {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
  align-content: start;
}
.hl li {
  display: flex;
  gap: 9px;
  padding: 9px 11px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
}
.hl b {
  font-size: 13.5px;
}
.hl p {
  margin: 2px 0 0;
}
.hl-icon {
  font-size: 17px;
  color: var(--accent);
  line-height: 1.3;
}
.status-grid {
  margin-top: 12px;
}
.env {
  display: grid;
  gap: 7px;
}
.env-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 5px;
  border-bottom: 1px dashed var(--line);
}
.hint {
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--warn);
  background: #fdf3e4;
  border: 1px solid #f2e0bf;
  border-radius: 9px;
  padding: 6px 8px;
}
.hint code {
  display: inline-block;
  margin-left: 4px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 0 5px;
  color: var(--ink);
}
.stats {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.stats > div {
  flex: 1;
  min-width: 90px;
  display: grid;
  gap: 0;
  padding: 7px 10px;
  border: 1px solid var(--line-2);
  border-radius: 11px;
  background: var(--panel-2);
}
.stats b {
  font-size: 21px;
}
.families {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 6px;
  margin-top: 10px;
}
.fam {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 650;
  color: var(--ink-2);
  padding: 5px 8px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--panel);
}
.fam:hover {
  text-decoration: none;
  border-color: #c3d2ea;
}
.fam i {
  width: 8px;
  height: 8px;
  border-radius: 3px;
}
.fam em {
  margin-left: auto;
  font-style: normal;
  color: var(--muted);
}
.progress-note {
  margin: 8px 0 0;
}
.grid.two {
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}
.algo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 12px;
}
.algo {
  display: grid;
  gap: 5px;
  align-content: start;
  padding: 12px 13px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-left-width: 3px;
  border-radius: 12px;
  color: var(--ink);
  box-shadow: var(--shadow);
}
.algo:hover {
  text-decoration: none;
  transform: translateY(-1px);
}
.algo-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}
.tagline {
  margin: 0;
  min-height: 2.9em;
}
.tags {
  gap: 4px;
}
.algo-foot {
  display: flex;
  justify-content: space-between;
  color: var(--muted);
}
.dots {
  letter-spacing: 2px;
  color: var(--accent-2);
}
@media (max-width: 900px) {
  .hero {
    grid-template-columns: 1fr;
  }
}
</style>
