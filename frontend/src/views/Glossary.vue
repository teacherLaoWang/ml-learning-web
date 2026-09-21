<script setup lang="ts">
/**
 * 术语速查：/api/glossary 汇总（后端 loader.glossary 把各篇 terms 去重合并）。
 * 支持中文/英文子串过滤，可按首字母或「出现在哪些算法」分组。
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import { backendState } from '../api'
import { loadGlossary, useGlossary } from '../composables/useGlossary'
import type { Term } from '../types'

const { terms, loading, loaded, count } = useGlossary()
const query = ref('')
const groupBy = ref<'letter' | 'algo'>('letter')

const filtered = computed<Term[]>(() => {
  const q = query.value.trim().toLowerCase()
  const list = terms.value ?? []
  if (!q) return list
  return list.filter(
    (t) =>
      t.term.toLowerCase().includes(q) ||
      (t.full ?? '').toLowerCase().includes(q) ||
      (t.explain ?? '').toLowerCase().includes(q),
  )
})

const groups = computed<Array<{ key: string; items: Term[] }>>(() => {
  const map = new Map<string, Term[]>()
  for (const t of filtered.value) {
    if (groupBy.value === 'letter') {
      const first = (t.term.trim()[0] ?? '#').toUpperCase()
      const key = /[A-Z0-9]/.test(first) ? first : '中文术语'
      map.set(key, [...(map.get(key) ?? []), t])
    } else {
      for (const k of t.keys?.length ? t.keys : ['其他']) {
        map.set(k, [...(map.get(k) ?? []), t])
      }
    }
  }
  return [...map.entries()]
    .map(([key, items]) => ({ key, items: items.sort((a, b) => a.term.localeCompare(b.term, 'zh-CN')) }))
    .sort((a, b) => a.key.localeCompare(b.key, 'zh-CN'))
})

onMounted(() => {
  void loadGlossary(true)
})
</script>

<template>
  <div class="glossary">
    <div class="card head">
      <div class="row-between">
        <div>
          <h1>术语速查表</h1>
          <p class="muted small">
            共 <b class="mono">{{ count }}</b> 条（来自各篇教案的 terms 汇总）。悬浮任何正文里的关键词也有同一个浮窗。
            <span v-if="backendState.mode === 'mock'" class="chip chip-mock tiny">离线演示术语</span>
          </p>
        </div>
        <div class="row">
          <input v-model="query" type="search" placeholder="搜中文 / 英文 / 释义…" aria-label="搜索术语" style="width: 220px" />
          <div class="seg">
            <button class="btn btn-sm" :class="{ 'btn-primary': groupBy === 'letter' }" @click="groupBy = 'letter'">按首字母</button>
            <button class="btn btn-sm" :class="{ 'btn-primary': groupBy === 'algo' }" @click="groupBy = 'algo'">按算法</button>
          </div>
        </div>
      </div>
    </div>

    <SkeletonBlock v-if="loading && !loaded" :lines="6" height="40px" label="正在读取 /api/glossary…" />
    <p v-else-if="!filtered.length" class="card muted">没有匹配「{{ query }}」的术语。换个说法试试（支持英文缩写与中文别名）。</p>

    <section v-for="g in groups" :key="g.key" class="group">
      <h2 class="g-key">{{ groupBy === 'algo' ? g.key : g.key }}<span class="chip tiny mono">{{ g.items.length }}</span></h2>
      <div class="terms">
        <article v-for="t in g.items" :key="t.term" class="term card card-tight">
          <div class="t-head">
            <b>{{ t.term }}</b>
            <em v-if="t.full" class="tiny muted">{{ t.full }}</em>
          </div>
          <p class="tiny">{{ t.explain }}</p>
          <div v-if="t.keys?.length" class="row links">
            <RouterLink v-for="k in t.keys.slice(0, 4)" :key="k" class="tiny" :to="`/algo/${k}`">{{ k }}</RouterLink>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.glossary {
  display: grid;
  gap: 12px;
}
.head h1 {
  margin: 0 0 4px;
  font-size: 23px;
}
.seg {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
}
.seg .btn {
  border: none;
  border-radius: 0;
}
.g-key {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  margin: 16px 0 8px;
  color: var(--accent-2);
}
.terms {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(268px, 1fr));
  gap: 10px;
}
.term {
  display: grid;
  gap: 3px;
  align-content: start;
}
.term:hover {
  border-color: #c3d2ea;
}
.t-head {
  display: flex;
  align-items: baseline;
  gap: 7px;
  flex-wrap: wrap;
}
.t-head b {
  font-size: 14px;
}
.term p {
  margin: 0;
  color: var(--ink-2);
}
.links {
  gap: 8px;
}
.links a {
  font-family: var(--mono);
}
</style>
