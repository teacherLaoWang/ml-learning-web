<script setup lang="ts">
/** 骨架屏：数据没到位时的占位（面板区一律先画这个，避免布局跳动） */
withDefaults(defineProps<{ lines?: number; height?: string; label?: string }>(), {
  lines: 3,
  height: '92px',
  label: '加载中…',
})
</script>

<template>
  <div class="skeleton-block">
    <div class="skeleton" :style="{ height, width: '100%' }" />
    <div v-for="i in lines" :key="i" class="skeleton line" :style="{ width: `${92 - i * 11}%` }" />
    <span class="tiny muted">{{ label }}</span>
  </div>
</template>

<style scoped>
.skeleton-block {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px dashed var(--line);
  border-radius: var(--radius);
  background: var(--panel);
}
.line {
  height: 11px;
}
</style>
