<script setup lang="ts">
/**
 * 渲染一片公式（行内或独立成块）。
 *
 * latex 为空或排版失败时回退成等宽原文 fallback —— 页面不会开天窗，
 * 也不会把没转录成功的 Unicode 公式悄悄显示成乱码。
 */
import { computed } from 'vue'
import { escapeHtml, texToHtml } from '../utils/tex'

const props = withDefaults(
  defineProps<{
    latex?: string
    /** 没有 latex 或排版失败时显示的原始文本 */
    fallback?: string
    display?: boolean
    /** 排版失败时把 LaTeX 源码原样标红（模型回答里比回退更清楚） */
    showRawOnError?: boolean
  }>(),
  { latex: '', fallback: '', display: false, showRawOnError: false },
)

const html = computed(() => texToHtml(props.latex ?? '', props.display))
const raw = computed(() => (props.showRawOnError ? escapeHtml((props.latex ?? '').trim()) : ''))
</script>

<template>
  <span v-if="html && !display" class="tex" v-html="html" />
  <div v-else-if="html" class="tex tex-block" v-html="html" />
  <code v-else-if="raw" class="tex-raw">{{ latex }}</code>
  <pre v-else-if="display && fallback" class="tex-fallback">{{ fallback }}</pre>
  <code v-else-if="fallback" class="tex-fallback-inline">{{ fallback }}</code>
</template>

<style scoped>
.tex {
  white-space: normal;
}
.tex-block {
  overflow-x: auto;
  overflow-y: hidden;
  padding: 2px 0;
}
.tex-block :deep(.katex-display) {
  margin: 0;
  text-align: left;
}
.tex-fallback,
.tex-fallback-inline {
  margin: 0;
  font-family: var(--mono);
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
}
:deep(.katex) {
  font-size: 1.06em;
}
.tex-raw {
  font-family: var(--mono);
  font-size: 12.5px;
  color: #f87171;
}
</style>
