<script setup lang="ts">
/**
 * 概念级提问面板：折叠时只是一个「问助教」小按钮，展开后是这一小节的小对话。
 *
 * 上下文由后端按 key + section 自己去教案里取（前端不传正文），
 * 所以这里只负责把「问哪一节、当前参数、前几轮问答」发出去。
 * 后端没配凭证时不显示按钮 —— 藏起来不如说明白，见 hint 分支。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { askState, askStream, loadAskStatus, type AskEvent } from '../api'
import { mdToHtml } from '../utils/md'

const props = withDefaults(
  defineProps<{
    algoKey: string
    section: Record<string, unknown>
    label: string
    /** 学生当前的滑块值，会作为上下文一起发过去 */
    params?: Record<string, number>
  }>(),
  { params: undefined },
)

interface Turn {
  role: 'user' | 'assistant'
  text: string
  meta?: string
}

const open = ref(false)
const input = ref('')
const turns = ref<Turn[]>([])
const busy = ref(false)
const err = ref('')
const bodyEl = ref<HTMLElement | null>(null)
let ctrl: AbortController | null = null

const status = computed(() => askState.status)
const ready = computed(() => !!status.value?.ready)
const last = computed(() => turns.value[turns.value.length - 1])

watch(open, (v) => {
  if (v && !status.value) void loadAskStatus()
})

async function scrollDown() {
  await nextTick()
  if (bodyEl.value) bodyEl.value.scrollTop = bodyEl.value.scrollHeight
}

function stop() {
  ctrl?.abort()
  ctrl = null
  busy.value = false
}

function html(turn: Turn): string {
  return turn.role === 'assistant' ? mdToHtml(turn.text) : ''
}

async function send() {
  const q = input.value.trim()
  if (!q || busy.value) return
  err.value = ''
  turns.value.push({ role: 'user', text: q })
  turns.value.push({ role: 'assistant', text: '' })
  const idx = turns.value.length - 1  // 只通过响应式数组改这一轮，别拿裸对象改
  input.value = ''
  busy.value = true
  void scrollDown()
  ctrl = new AbortController()
  const my = ctrl
  const history = turns.value.slice(0, -2).map((t) => ({ role: t.role, text: t.text }))

  const onEvent = (e: AskEvent) => {
    const cur = turns.value[idx]
    if (!cur) return
    if (e.type === 'delta') cur.text += e.text
    else if (e.type === 'error') err.value = e.message
    else if (e.type === 'done') {
      const bits: string[] = []
      if (e.ms) bits.push(`${(e.ms / 1000).toFixed(1)}s`)
      if (typeof e.costUsd === 'number' && e.costUsd > 0) bits.push(`约 $${e.costUsd.toFixed(4)}`)
      cur.meta = bits.join(' · ')
    }
    void scrollDown()
  }
  try {
    await askStream(
      { key: props.algoKey, section: props.section, question: q, params: props.params, history },
      onEvent,
      my.signal,
    )
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError')) err.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (ctrl === my) {
      busy.value = false
      ctrl = null
    }
  }
}

function retry() {
  const q = [...turns.value].reverse().find((t) => t.role === 'user')?.text ?? ''
  if (!q) return
  if (last.value?.role === 'assistant' && !last.value.text) turns.value.pop()
  input.value = q
  void send()
}

function onKey(ev: KeyboardEvent) {
  if (ev.key === 'Escape') {
    stop()
    open.value = false
    ev.stopPropagation()
  } else if (ev.key === 'Enter' && !ev.shiftKey) {
    ev.preventDefault()
    void send()
  }
}
</script>

<template>
  <span class="ask">
    <button v-if="!open" class="ask-chip" :class="{ dim: status && !ready }" :title="status?.ready ? `就问「${label}」这一节` : status?.reason ?? '检查提问能力…'" @click="open = true">
      问助教
    </button>

    <span v-else-if="status && !ready" class="ask-note">
      {{ status.reason }}
      <button class="linkish" @click="open = false">收起</button>
    </span>

    <span v-else-if="!status" class="ask-note tiny">检查提问能力…</span>

    <div v-else class="ask-panel">
      <div class="ask-head">
        <b>问助教 · {{ label }}</b>
        <span class="tiny muted">{{ status.model ? `模型 ${status.model}` : '' }}</span>
        <button class="linkish" @click="stop(); open = false">收起</button>
      </div>

      <div v-if="turns.length" ref="bodyEl" class="ask-body">
        <div v-for="(t, i) in turns" :key="i" class="turn" :class="t.role">
          <p v-if="t.role === 'user'" class="q">{{ t.text }}</p>
          <template v-else>
            <div v-if="t.text" class="a" v-html="html(t)" />
            <p v-else-if="busy && i === turns.length - 1" class="a waiting">正在想…</p>
            <p v-if="t.meta" class="meta tiny muted">{{ t.meta }} · {{ status.note }}</p>
          </template>
        </div>
      </div>

      <p v-if="err" class="ask-err">
        {{ err }}
        <button class="linkish" @click="retry">重试</button>
      </p>

      <div class="ask-input">
        <textarea
          v-model="input"
          rows="2"
          :placeholder="`关于「${label}」问点什么，例如：这一步为什么要除以 n−1？`"
          @keydown="onKey"
        />
        <div class="ask-btns">
          <button v-if="busy" class="ghost" @click="stop">停止</button>
          <button class="primary" :disabled="busy || !input.trim()" @click="send">{{ busy ? '回答中…' : '发送' }}</button>
        </div>
      </div>
    </div>
  </span>
</template>

<style scoped>
.ask {
  display: inline-block;
}
.ask-chip {
  font-size: 11px;
  line-height: 1.4;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px dashed var(--line-2);
  background: transparent;
  color: var(--muted, #64748b);
  cursor: pointer;
}
.ask-chip:hover {
  border-style: solid;
  color: var(--accent);
}
.ask-chip.dim {
  opacity: 0.55;
}
.ask-panel {
  display: block;
  margin: 8px 0 2px;
  padding: 8px 10px;
  border: 1px solid var(--line-2);
  border-left: 3px solid var(--accent);
  border-radius: 10px;
  background: var(--panel-2);
}
.ask-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 6px;
}
.ask-body {
  max-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.q {
  margin: 0;
  font-size: 12.5px;
  color: var(--text, #e2e8f0);
  background: rgba(148, 163, 184, 0.12);
  border-radius: 8px;
  padding: 4px 8px;
  white-space: pre-wrap;
}
.a {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
}
.a :deep(p) {
  margin: 4px 0;
}
.a :deep(ul),
.a :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}
.a :deep(code) {
  font-family: var(--mono);
  font-size: 12px;
  background: rgba(148, 163, 184, 0.16);
  border-radius: 4px;
  padding: 0 4px;
}
.a :deep(.md-block-math) {
  margin: 6px 0;
  overflow-x: auto;
}
.waiting {
  color: var(--muted, #64748b);
}
.meta {
  margin: 2px 0 0;
}
.ask-err {
  margin: 6px 0 0;
  font-size: 12px;
  color: #f87171;
}
.ask-input textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  font: inherit;
  font-size: 12.5px;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid var(--line-2);
  background: var(--panel, #0b1120);
  color: inherit;
}
.ask-btns {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 5px;
}
button {
  font: inherit;
  cursor: pointer;
}
.primary {
  font-size: 12px;
  padding: 3px 12px;
  border-radius: 8px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
}
.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ghost {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 8px;
  border: 1px solid var(--line-2);
  background: transparent;
  color: inherit;
}
.linkish {
  border: 0;
  background: none;
  color: var(--accent);
  font-size: 12px;
  padding: 0;
  margin-left: auto;
}
.ask-note {
  display: inline-block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted, #64748b);
}
</style>
