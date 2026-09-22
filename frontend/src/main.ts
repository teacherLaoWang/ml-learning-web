import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import 'katex/dist/katex.min.css'
import './styles/base.css'
import { loadGlossary } from './composables/useGlossary'

loadGlossary()
createApp(App).use(router).mount('#app')

// 本机自测钩子：/algo 页面的 3D 文字布局可被自动化脚本读取（叠字 / 出框检查）
if (['localhost', '127.0.0.1'].includes(location.hostname)) {
  void import('./three/engine').then(({ liveEngines }) => {
    ;(window as unknown as Record<string, unknown>).__ml3d = {
      engines: liveEngines,
      labelRects: () => liveEngines().flatMap((e) => e.labelScreenRects()),
      viewports: () => liveEngines().map((e) => e.viewportSize()),
    }
  })
}
