<script setup lang="ts">
/**
 * 正文自动标注：把已知关键词（NN/SGD/MSE/Gini…）包成 TermTip（§3.3）。
 * plain 模式用于短文本（滑杆 label、hint），不换行、不加大括号。
 */
import { computed } from 'vue'
import TermTip from './TermTip.vue'
import { useGlossary } from '../composables/useGlossary'

const props = withDefaults(defineProps<{ text: string; plain?: boolean }>(), { plain: false })

const { pattern } = useGlossary()

interface Seg {
  key: string
  term: boolean
  v: string
}

const segs = computed<Seg[]>(() => {
  const text = props.text ?? ''
  const re = pattern.value
  if (!text) return []
  if (!re) return [{ key: 'p0', term: false, v: text }]
  const out: Seg[] = []
  re.lastIndex = 0
  let last = 0
  let m: RegExpExecArray | null
  let guard = 0
  while ((m = re.exec(text)) && guard++ < 400) {
    if (m.index > last) out.push({ key: `p${last}`, term: false, v: text.slice(last, m.index) })
    out.push({ key: `t${m.index}`, term: true, v: m[0] })
    last = m.index + m[0].length
    if (m[0].length === 0) re.lastIndex++
  }
  if (last < text.length) out.push({ key: `p${last}`, term: false, v: text.slice(last) })
  return out
})
</script>

<template>
  <span class="lesson-text" :class="{ plain }"><template v-for="s in segs" :key="s.key"><TermTip v-if="s.term" :term="s.v">{{ s.v }}</TermTip><template v-else>{{ s.v }}</template></template></span>
</template>

<style scoped>
.lesson-text.plain {
  color: inherit;
}
</style>
