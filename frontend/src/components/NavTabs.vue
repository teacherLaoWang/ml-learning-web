<script setup lang="ts">
/** 顶部固定页签：站点导航 + X-Backend 状态（live / mock）+ 强制离线开关 */
import { backendState } from '../api'
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <nav class="nav">
    <div class="nav-inner">
      <RouterLink to="/" class="brand">
        <span class="logo">▦</span>
        <span class="brand-text">
          ML 3D 仿真台
          <small>可旋转 · 可单步 · 可暂停的机器学习教室</small>
        </span>
      </RouterLink>

      <div class="tabs">
        <RouterLink to="/" class="tab" active-class="" exact-active-class="on">首页</RouterLink>
        <RouterLink to="/catalog" class="tab" active-class="on">全景目录</RouterLink>
        <RouterLink to="/glossary" class="tab" active-class="on">术语表</RouterLink>
      </div>

      <div class="row status">
        <span class="chip" :class="backendState.mode === 'live' ? 'chip-ok' : 'chip-mock'" :title="backendState.lastError">
          <i class="dot" :class="backendState.mode === 'live' ? 'live' : 'mock'" />
          X-Backend: {{ backendState.forceMock ? 'mock（手动）' : backendState.mode }}
        </span>
        <button
          class="btn btn-sm"
          :class="{ 'btn-primary': backendState.forceMock }"
          :title="backendState.forceMock ? '回到真实后端' : '不连后端，用 fixtures 逛完整站'"
          @click="backendState.forceMock = !backendState.forceMock"
        >
          {{ backendState.forceMock ? '退出离线演示' : '离线演示' }}
        </button>
        <button class="btn btn-sm" title="重新探测后端" @click="router.go(0)">重连</button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: var(--nav-h);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: saturate(1.4) blur(8px);
  border-bottom: 1px solid var(--line);
  z-index: 50;
}
.nav-inner {
  max-width: 1320px;
  margin: 0 auto;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 16px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-weight: 800;
  font-size: 15px;
  white-space: nowrap;
}
.brand:hover {
  text-decoration: none;
}
.brand-text small {
  display: block;
  font-weight: 500;
  color: var(--muted);
  font-size: 11px;
}
.logo {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: #fff;
  font-size: 14px;
}
.tabs {
  display: flex;
  gap: 4px;
  margin-left: 6px;
}
.tab {
  padding: 5px 11px;
  border-radius: 999px;
  font-size: 13.5px;
  font-weight: 650;
  color: var(--ink-2);
}
.tab:hover {
  background: var(--panel-2);
  text-decoration: none;
}
.tab.on {
  background: #e8efff;
  color: #1e40af;
}
.status {
  margin-left: auto;
  gap: 6px;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.dot.live {
  background: #16a34a;
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.18);
}
.dot.mock {
  background: #dc2626;
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.16);
}
@media (max-width: 860px) {
  .brand-text small,
  .status .btn {
    display: none;
  }
  .nav-inner {
    gap: 8px;
  }
}
</style>
