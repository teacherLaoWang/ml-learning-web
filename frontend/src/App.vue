<script setup lang="ts">
/** 站点外壳：固定页签 + 醒目的离线演示标注 + 路由视图 + 环境探测 */
import { onMounted, ref } from 'vue'
import NavTabs from './components/NavTabs.vue'
import { backendState, getEnv } from './api'
import { useDocumentVisible } from './composables/useVisibility'

// 让 body.is-hidden 在全站生效（骨架屏等 CSS 动画随之暂停）
useDocumentVisible()

const envHint = ref('')
const probing = ref(false)

async function probe() {
  probing.value = true
  try {
    const env = await getEnv()
    envHint.value = env.hint ?? ''
  } catch (e) {
    envHint.value = e instanceof Error ? e.message : String(e)
  } finally {
    probing.value = false
  }
}

onMounted(() => {
  void probe()
})
</script>

<template>
  <NavTabs />
  <div class="app-shell">
    <div class="wrap">
      <Transition name="slide">
        <div v-if="backendState.mode === 'mock'" class="mock-banner" role="status">
          <span>
            离线演示数据（mock）—— 后端 <code>/api</code> 没连上，目录、教案、术语与 3D 动画全部走
            <code>src/fixtures/*.json</code>，功能完整可逛。
            <span v-if="backendState.lastError" class="tiny reason">原因：{{ backendState.lastError }}</span>
          </span>
          <span class="row">
            <button class="btn btn-sm" :disabled="probing" @click="probe">{{ probing ? '探测中…' : '重试连接' }}</button>
            <button class="btn btn-sm" @click="backendState.forceMock = false; probe()">回到实时后端</button>
          </span>
        </div>
      </Transition>

      <RouterView />

      <footer class="foot tiny muted">
        契约：<code>docs/API-CONTRACT.md</code> · 内核：<code>app/ml/*</code>（NumPy，装了 PyTorch 自动升级）·
        前端：Vite + Vue 3 + three.js，完全离线可用（无 CDN / 不联网）
        <span v-if="envHint"> · {{ envHint }}</span>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.wrap .mock-banner {
  margin-bottom: 12px;
}
.reason {
  display: block;
  font-weight: 500;
  opacity: 0.8;
}
.foot {
  margin-top: 28px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  text-align: center;
}
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
