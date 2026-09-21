<script setup lang="ts">
/**
 * 参数面板：完全由后端 PARAM_SPECS（`catalog.PARAM_SPECS`）驱动 ——
 * 有 options 就是离散选择，否则是滑杆 + 数字框；不做任何算法专属硬编码。
 */
import type { ParamSpec, Preset } from '../types'
import LessonText from './LessonText.vue'
import { clampParam } from '../api'
import { fmtParam } from '../utils/format'

const props = withDefaults(
  defineProps<{
    specs: ParamSpec[]
    modelValue: Record<string, number>
    presets?: Preset[]
    seed: number
    steps: number
    busy?: boolean
    disabled?: boolean
    title?: string
  }>(),
  { presets: () => [], busy: false, disabled: false, title: '参数' },
)

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, number>]
  'update:seed': [value: number]
  'update:steps': [value: number]
  run: []
  reset: []
}>()

const STEP_MIN = 8
const STEP_MAX = 400

function valueOf(spec: ParamSpec): number {
  const v = props.modelValue[spec.id]
  return v === undefined || !Number.isFinite(v) ? spec.default : v
}

function setParam(spec: ParamSpec, raw: number) {
  const next = { ...props.modelValue, [spec.id]: clampParam(spec, raw) }
  emit('update:modelValue', next)
}

function fillPct(spec: ParamSpec): string {
  const span = spec.max - spec.min || 1
  return `${((valueOf(spec) - spec.min) / span) * 100}%`
}

function applyPreset(preset: Preset) {
  const next = { ...props.modelValue }
  for (const [k, v] of Object.entries(preset.params)) {
    const spec = props.specs.find((s) => s.id === k)
    next[k] = spec ? clampParam(spec, Number(v)) : Number(v)
  }
  emit('update:modelValue', next)
  emit('run')
}

function rollSeed() {
  emit('update:seed', Math.floor(Math.random() * 9999) + 1)
  emit('run')
}

function valueOfId(id: string): number {
  const spec = props.specs.find((s) => s.id === id)
  const v = props.modelValue[id]
  return spec ? valueOf(spec) : Number(v)
}

const activePreset = (preset: Preset): boolean =>
  Object.entries(preset.params).every(([k, v]) => Math.abs(Number(v) - valueOfId(k)) < 1e-9)
</script>

<template>
  <section class="params card">
    <div class="card-head">
      <h3>{{ title }}</h3>
      <span v-if="busy" class="chip chip-accent">计算中…</span>
    </div>

    <p v-if="!specs.length" class="muted small">
      这个算法没有仿真台（目录里 status = outline），只展示概念卡片。
    </p>

    <div v-for="spec in specs" :key="spec.id" class="param">
      <div class="param-top">
        <label :for="`p-${spec.id}`">
          <LessonText :text="spec.label" plain />
        </label>
        <span class="param-value mono">{{ fmtParam(valueOf(spec)) }}</span>
      </div>

      <div v-if="spec.options && spec.options.length" class="seg" role="group">
        <button
          v-for="opt in spec.options"
          :key="opt.value"
          class="btn btn-sm"
          :class="{ 'btn-primary': valueOf(spec) === opt.value }"
          :disabled="disabled"
          @click="setParam(spec, opt.value)"
        >
          {{ opt.label }}
        </button>
      </div>

      <div v-else class="slider-row">
        <input
          :id="`p-${spec.id}`"
          type="range"
          class="slider"
          :min="spec.min"
          :max="spec.max"
          :step="spec.step"
          :value="valueOf(spec)"
          :disabled="disabled"
          :style="{ '--fill': fillPct(spec) }"
          @input="setParam(spec, Number(($event.target as HTMLInputElement).value))"
        />
        <input
          type="number"
          :min="spec.min"
          :max="spec.max"
          :step="spec.step"
          :value="valueOf(spec)"
          :disabled="disabled"
          @change="setParam(spec, Number(($event.target as HTMLInputElement).value))"
        />
      </div>

      <p v-if="spec.hint" class="hint tiny">
        <LessonText :text="spec.hint" plain />
      </p>
      <p class="range-note tiny mono">{{ spec.min }} … {{ spec.max }} · 步长 {{ spec.step }}</p>
    </div>

    <div v-if="presets.length" class="presets">
      <span class="tiny muted">预设：</span>
      <button
        v-for="p in presets"
        :key="p.id"
        class="btn btn-sm chip-like"
        :class="{ 'btn-primary': activePreset(p) }"
        :disabled="disabled"
        :title="Object.entries(p.params).map(([k, v]) => `${k}=${v}`).join(' · ')"
        @click="applyPreset(p)"
      >
        {{ p.label }}
      </button>
    </div>

    <div class="param">
      <div class="param-top">
        <label for="p-steps">训练步数 steps</label>
        <span class="param-value mono">{{ steps }}</span>
      </div>
      <div class="slider-row">
        <input
          id="p-steps"
          type="range"
          class="slider"
          :min="STEP_MIN"
          :max="STEP_MAX"
          :step="STEP_MIN"
          :style="{ '--fill': `${((steps - STEP_MIN) / (STEP_MAX - STEP_MIN)) * 100}%` }"
          :disabled="disabled"
          @input="emit('update:steps', Number(($event.target as HTMLInputElement).value))"
        />
        <span class="tiny muted nowrap">上限 {{ STEP_MAX }}（后端会钳制）</span>
      </div>
    </div>

    <div class="row seed-row">
      <label for="p-seed" class="tiny muted">随机种子</label>
      <input
        id="p-seed"
        type="number"
        :value="seed"
        min="0"
        max="99999"
        :disabled="disabled"
        @change="emit('update:seed', Number(($event.target as HTMLInputElement).value))"
      />
      <button class="btn btn-sm" :disabled="disabled" @click="rollSeed">换一个</button>
      <span class="tiny muted">同 seed 同轨迹（可复现）</span>
    </div>

    <div class="row btn-row">
      <button class="btn btn-primary" :disabled="disabled || busy" @click="emit('run')">应用并重跑</button>
      <button class="btn" :disabled="disabled" @click="emit('reset')">恢复默认</button>
    </div>
  </section>
</template>

<style scoped>
.params {
  display: grid;
  gap: 4px;
}
.param {
  padding: 7px 0 3px;
  border-top: 1px dashed var(--line);
}
.param:first-of-type {
  border-top: none;
}
.param-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.param-top label {
  font-weight: 650;
  font-size: 13.5px;
}
.param-value {
  color: var(--accent);
  font-weight: 700;
}
.slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.slider {
  flex: 1;
  min-width: 120px;
}
.seg {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 5px;
}
.hint {
  color: var(--muted);
  margin: 3px 0 0;
}
.range-note {
  color: #93a3bd;
  margin: 1px 0 0;
}
.presets {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  padding: 8px 0 2px;
  border-top: 1px dashed var(--line);
}
.chip-like {
  border-radius: 999px;
}
.seed-row {
  padding-top: 8px;
  border-top: 1px dashed var(--line);
}
.btn-row {
  padding-top: 10px;
}
</style>
