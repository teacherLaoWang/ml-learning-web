<script setup lang="ts">
/** 公式卡：排版过的公式 + 符号释义 + 代入真实数字的算例（§4 三件套） */
import type { Formula } from '../types'
import KatexChip from './KatexChip.vue'
import LessonText from './LessonText.vue'

defineProps<{ formula: Formula; title?: string }>()
</script>

<template>
  <section v-if="formula?.text || formula?.vars?.length" class="formula card">
    <div class="card-head">
      <h3>{{ title ?? '公式' }}</h3>
      <span class="chip tiny">符号 + 释义 + 算例</span>
    </div>
    <KatexChip class="main-tex" display :latex="formula.latex" :fallback="formula.text" />
    <table v-if="formula.vars?.length" class="vars">
      <tbody>
        <tr v-for="(v, i) in formula.vars" :key="i">
          <th class="sym"><KatexChip :latex="v.latex" :fallback="v.sym" showRawOnError /></th>
          <td>
            <LessonText :text="v.zh" />
            <span v-if="v.example" class="eg mono">例：{{ v.example }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.main-tex {
  display: block;
  margin: 0;
  padding: 10px 12px;
  background: #0d1424;
  color: #e8eefc;
  border-radius: 10px;
  font-size: 14.5px;
  line-height: 1.9;
}
.vars {
  width: 100%;
  border-collapse: collapse;
  margin-top: 8px;
  font-size: 13px;
}
.vars th,
.vars td {
  text-align: left;
  padding: 5px 6px;
  border-top: 1px solid var(--line-2);
  vertical-align: top;
}
.vars th {
  width: 78px;
  color: var(--accent);
  font-weight: 700;
}
.eg {
  display: inline-block;
  margin-left: 6px;
  color: var(--ok);
  font-size: 12px;
}
</style>
