<script setup lang="ts">
/** 通用表格卡：契约 table[] 的 rows 只有 name/value/truth/delta/note 四种可选列 */
import { computed } from 'vue'
import type { TableCard } from '../types'

const props = defineProps<{ table: TableCard }>()

const cols = computed(() => {
  const rows = props.table?.rows ?? []
  const has = (k: 'value' | 'truth' | 'delta' | 'note') => rows.some((r) => r[k] !== undefined && r[k] !== '')
  return [
    { key: 'value' as const, label: '本次' },
    { key: 'truth' as const, label: '参照/真值' },
    { key: 'delta' as const, label: '偏差' },
    { key: 'note' as const, label: '备注' },
  ].filter((c) => has(c.key))
})
</script>

<template>
  <section v-if="table?.rows?.length" class="table-card card card-tight">
    <div class="card-head">
      <h3>{{ table.title || table.id }}</h3>
      <span class="chip tiny mono">{{ table.rows.length }} 行</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>名称</th>
          <th v-for="c in cols" :key="c.key">{{ c.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in table.rows" :key="i">
          <td class="name">{{ r.name }}</td>
          <td v-for="c in cols" :key="c.key" class="mono" :class="c.key">
            {{ r[c.key] ?? '—' }}
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.table-card {
  overflow-x: auto;
}
.table-card h3 {
  margin: 0;
  font-size: 13.5px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  text-align: left;
  padding: 5px 8px;
  border-bottom: 1px solid var(--line-2);
  white-space: nowrap;
}
thead th {
  color: var(--muted);
  font-size: 11.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
td.name {
  font-weight: 650;
}
td.delta {
  color: var(--warn);
}
td.note {
  color: var(--muted);
  white-space: normal;
}
tbody tr:hover {
  background: var(--panel-2);
}
</style>
