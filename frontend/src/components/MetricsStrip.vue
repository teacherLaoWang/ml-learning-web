<script setup lang="ts">
/** 指标条：由 METRIC_SPEC 驱动，缺哪个显示「—」；顺带把 backend / 用时 / 步数 / seed 交代清楚 */
import { computed } from 'vue'
import type { MetricSpec, Metrics } from '../types'
import { fmtInt, fmtNum } from '../utils/format'
import TermTip from './TermTip.vue'

const props = withDefaults(
  defineProps<{
    specs: MetricSpec[]
    metrics: Metrics
    backend?: string
    elapsedMs?: number
    steps?: number
    seed?: number
    mock?: boolean
    resumed?: boolean
  }>(),
  { backend: '', elapsedMs: undefined, steps: 0, seed: 0, mock: false, resumed: false },
)

function valueOf(id: string): string {
  const v = props.metrics?.[id]
  if (v === undefined || v === null) return '—'
  if (typeof v === 'string') return v
  return fmtNum(v, 4)
}

const note = computed(() => (typeof props.metrics?.note === 'string' ? (props.metrics.note as string) : ''))
</script>

<template>
  <section class="metrics card card-tight">
    <div class="row chips">
      <div v-for="m in specs" :key="m.id" class="metric">
        <span class="m-label">{{ m.label }}</span>
        <span class="m-value mono">{{ valueOf(m.id) }}</span>
      </div>
      <div class="metric meta">
        <span class="m-label">内核</span>
        <span class="m-value mono">{{ backend || '—' }}</span>
      </div>
      <div v-if="elapsedMs !== undefined && !mock" class="metric meta">
        <span class="m-label">用时</span>
        <span class="m-value mono">{{ fmtInt(elapsedMs) }} ms</span>
      </div>
      <div class="metric meta">
        <span class="m-label">steps</span>
        <span class="m-value mono">{{ fmtInt(steps) }}</span>
      </div>
      <div class="metric meta">
        <span class="m-label">seed</span>
        <span class="m-value mono">{{ fmtInt(seed) }}</span>
      </div>
    </div>
    <div class="row foot tiny">
      <span v-if="mock" class="chip chip-mock">离线演示数据（mock）：数值来自 fixtures，不随参数变化</span>
      <span v-if="resumed" class="chip chip-ok">/step 续算</span>
      <span v-if="note">{{ note }}</span>
      <TermTip v-else term="metrics" explain="评估数字。同一个模型换指标会得到不同结论，所以先定指标再调参。">
        <span class="muted">指标怎么读？</span>
      </TermTip>
    </div>
  </section>
</template>

<style scoped>
.metrics {
  display: grid;
  gap: 4px;
}
.chips {
  gap: 8px;
}
.metric {
  display: grid;
  gap: 1px;
  padding: 4px 10px;
  border-radius: 10px;
  background: var(--panel-2);
  border: 1px solid var(--line-2);
  min-width: 82px;
}
.metric.meta {
  background: transparent;
  border-style: dashed;
}
.m-label {
  font-size: 11px;
  color: var(--muted);
  font-weight: 700;
}
.m-value {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
}
.foot {
  justify-content: flex-start;
  color: var(--muted);
  gap: 8px;
}
</style>
