<script setup lang="ts">
/**
 * 正文渲染：先按 $...$ 切出公式交给 KaTeX，剩下的散文再做关键词标注
 * （NN/SGD/MSE/Gini… → TermTip，§3.3）。公式内部不做术语匹配，
 * 否则 \sigma 里的 "sig" 之类会被当成术语套上虚线。
 * plain 模式用于短文本（滑杆 label、hint），不换行、不加大括号。
 */
import { computed } from 'vue'
import KatexChip from './KatexChip.vue'
import TermTip from './TermTip.vue'
import { splitMath } from '../utils/tex'
import { useGlossary } from '../composables/useGlossary'

const props = withDefaults(defineProps<{ text: string; plain?: boolean }>(), { plain: false })

const { pattern } = useGlossary()

interface Seg {
  key: string
  math: boolean
  term: boolean
  v: string
}

const segs = computed<Seg[]>(() => {
  const text = props.text ?? ''
  if (!text) return []
  const out: Seg[] = []
  const re = pattern.value
  if (re) re.lastIndex = 0
  let guard = 0
  for (const part of splitMath(text)) {
    if (part.math) {
      out.push({ key: `m${out.length}`, math: true, term: false, v: part.v })
      continue
    }
    let last = 0
    let m: RegExpExecArray | null
    if (!re) {
      out.push({ key: `p${last}`, math: false, term: false, v: part.v })
      continue
    }
    re.lastIndex = 0  // 全局正则换字符串前必须归零，否则从上一段的偏移继续找
    while ((m = re.exec(part.v)) && guard++ < 400) {
      if (m.index > last) out.push({ key: `p${m.index}`, math: false, term: false, v: part.v.slice(last, m.index) })
      out.push({ key: `t${m.index}`, math: false, term: true, v: m[0] })
      last = m.index + m[0].length
      if (m[0].length === 0) re.lastIndex++
    }
    if (last < part.v.length) out.push({ key: `p${last}e`, math: false, term: false, v: part.v.slice(last) })
  }
  return out
})
</script>

<template>
  <span class="lesson-text" :class="{ plain }">
    <template v-for="s in segs" :key="s.key">
      <KatexChip v-if="s.math" :latex="s.v" showRawOnError />
      <TermTip v-else-if="s.term" :term="s.v">{{ s.v }}</TermTip>
      <template v-else>{{ s.v }}</template>
    </template>
  </span>
</template>

<style scoped>
.lesson-text.plain {
  color: inherit;
}
</style>
