<script setup lang="ts">
/**
 * 全景目录：/api/catalog 按六大类分组。
 * ready → 可点进仿真台；outline → 就地展开「概念卡片」（只读教案文字，没有仿真台）。
 */
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import LessonText from '../components/LessonText.vue'
import TermTip from '../components/TermTip.vue'
import { getAlgorithm, getCatalog } from '../api'
import type { Algorithm, CatalogItem, Family } from '../types'

/** 术语小胶囊：复用 TermTip 的浮窗与视口避让 */
const TermChip = defineComponent({
  name: 'TermChip',
  props: { term: { type: String, required: true } },
  setup(props) {
    return () => h('span', { class: 'chip tiny' }, [h(TermTip, { term: props.term })])
  },
})

const catalog = ref<Family[]>([])
const loading = ref(true)
const error = ref('')
const query = ref('')
const onlyReady = ref(false)
const totals = ref({ ready: 0, total: 0 })

const concept = ref<Record<string, Algorithm | null>>({})
const openKey = ref('')
const conceptLoading = ref('')

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return catalog.value
    .map((f) => ({
      ...f,
      items: f.items.filter((it) => {
        if (onlyReady.value && it.status !== 'ready') return false
        if (!q) return true
        return (
          it.name.toLowerCase().includes(q) ||
          it.key.toLowerCase().includes(q) ||
          (it.tagline ?? '').toLowerCase().includes(q) ||
          it.tags.some((t) => t.toLowerCase().includes(q))
        )
      }),
    }))
    .filter((f) => f.items.length)
})

const stats = computed(() => {
  const ready = totals.value.ready || filtered.value.flatMap((f) => f.items).filter((i) => i.status === 'ready').length
  return { ready, total: totals.value.total || filtered.value.flatMap((f) => f.items).length }
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const c = await getCatalog()
    catalog.value = c.families
    totals.value = { ready: c.readyCount ?? 0, total: c.totalCount ?? 0 }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function toggleConcept(item: CatalogItem) {
  if (item.status === 'ready') return
  if (openKey.value === item.key) {
    openKey.value = ''
    return
  }
  openKey.value = item.key
  if (concept.value[item.key] !== undefined) return
  conceptLoading.value = item.key
  try {
    concept.value[item.key] = await getAlgorithm(item.key)
  } catch (e) {
    concept.value[item.key] = null
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    conceptLoading.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="catalog">
    <div class="card head">
      <div class="row-between">
        <div>
          <h1>算法全景目录</h1>
          <p class="muted small">
            {{ stats.total }} 个条目，{{ stats.ready }} 个已精做为可交互仿真台；其余是概念卡片（先讲清楚「它解决什么问题」）。
          </p>
        </div>
        <div class="row">
          <input v-model="query" type="search" placeholder="搜名称 / key / 标签…" aria-label="搜索算法" />
          <button class="btn btn-sm" :class="{ 'btn-primary': onlyReady }" @click="onlyReady = !onlyReady">只看 ready</button>
        </div>
      </div>
    </div>

    <div v-if="error" class="err-banner">{{ error }}</div>
    <SkeletonBlock v-if="loading" :lines="5" height="120px" label="正在读取 /api/catalog…" />

    <section v-for="f in filtered" :id="f.key" :key="f.key" class="family">
      <header class="fam-head" :style="{ borderColor: `${f.color}55` }">
        <i class="bar" :style="{ background: f.color }" />
        <div>
          <h2>{{ f.name }} <span class="chip tiny mono">{{ f.items.length }}</span></h2>
          <p class="tiny muted">{{ f.blurb }}</p>
        </div>
      </header>

      <div class="items">
        <template v-for="it in f.items" :key="it.key">
          <component
            :is="it.status === 'ready' ? RouterLink : 'button'"
            class="item"
            :class="{ outline: it.status !== 'ready', open: openKey === it.key }"
            :style="{ borderLeftColor: f.color }"
            :to="it.status === 'ready' ? `/algo/${it.key}` : undefined"
            :aria-expanded="it.status === 'ready' ? undefined : openKey === it.key"
            @click="it.status === 'ready' ? undefined : toggleConcept(it)"
          >
            <div class="item-top">
              <b>{{ it.name }}</b>
              <span class="row gap0">
                <span class="chip tiny mono">{{ it.key }}</span>
                <span class="chip tiny" :class="it.status === 'ready' ? 'chip-ok' : ''">
                  {{ it.status === 'ready' ? '仿真台' : '概念卡片' }}
                </span>
              </span>
            </div>
            <p class="tiny muted item-tag">{{ it.tagline || '点开看讲解' }}</p>
            <div class="row tags">
              <span v-for="t in it.tags" :key="t" class="chip tiny">{{ t }}</span>
              <span class="tiny mono lvl">{{ '●'.repeat(it.difficulty) }}{{ '○'.repeat(Math.max(0, 5 - it.difficulty)) }}</span>
            </div>
            <span v-if="it.status !== 'ready'" class="tiny more">{{ openKey === it.key ? '▲ 收起' : '▼ 展开只读教案' }}</span>
          </component>

          <div v-if="openKey === it.key" class="concept card">
            <SkeletonBlock v-if="conceptLoading === it.key" :lines="3" height="34px" label="正在读取教案…" />
            <template v-else-if="concept[it.key]">
              <div class="card-head">
                <h3>{{ concept[it.key]!.name }} · 概念卡片</h3>
                <span class="chip tiny">无仿真台</span>
              </div>
              <p><LessonText :text="concept[it.key]!.story" /></p>
              <ul>
                <li v-for="(p, i) in concept[it.key]!.intuition" :key="i"><LessonText :text="p" /></li>
              </ul>
              <p v-for="(p, i) in concept[it.key]!.pitfalls" :key="`pf${i}`" class="pit tiny">
                <b>坑：</b><LessonText :text="p" />
              </p>
              <div v-if="concept[it.key]!.terms?.length" class="row terms">
                <TermChip v-for="t in concept[it.key]!.terms.slice(0, 8)" :key="t.term" :term="t.term" />
              </div>
            </template>
            <p v-else class="tiny muted">
              后端还没写这篇教案（app/content/lessons/{{ it.key }}.py）。目录里的标签与定位说明仍然可读。
            </p>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>


<style scoped>
.catalog {
  display: grid;
  gap: 14px;
}
.head h1 {
  margin: 0 0 4px;
  font-size: 23px;
}
.family {
  margin-top: 6px;
  scroll-margin-top: 70px;
}
.fam-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  border-left: 4px solid;
  padding: 4px 0 4px 10px;
  margin-bottom: 8px;
}
.fam-head .bar {
  display: none;
}
.fam-head h2 {
  margin: 0;
  font-size: 17px;
  display: flex;
  align-items: center;
  gap: 7px;
}
.fam-head p {
  margin: 2px 0 0;
}
.items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(258px, 1fr));
  gap: 10px;
}
.item {
  display: grid;
  gap: 4px;
  align-content: start;
  text-align: left;
  font: inherit;
  color: inherit;
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 3px solid;
  border-radius: 12px;
  padding: 10px 12px;
  cursor: pointer;
  box-shadow: var(--shadow);
}
.item:hover {
  text-decoration: none;
  transform: translateY(-1px);
}
.item.outline {
  background: var(--panel-2);
  box-shadow: none;
}
.item.open {
  border-color: var(--accent);
}
.item-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}
.gap0 {
  gap: 4px;
}
.item-tag {
  margin: 0;
  min-height: 2.6em;
}
.tags {
  gap: 4px;
}
.lvl {
  margin-left: auto;
  color: var(--muted);
  letter-spacing: 1px;
}
.more {
  color: var(--accent);
  font-weight: 700;
}
.concept {
  grid-column: 1 / -1;
  background: #fbfcff;
}
.concept ul {
  margin: 0 0 8px;
  padding-left: 20px;
}
.pit {
  color: var(--warn);
  margin: 0 0 4px;
}
.terms {
  gap: 5px;
}
</style>
