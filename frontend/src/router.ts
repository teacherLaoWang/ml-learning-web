import { createRouter, createWebHashHistory } from 'vue-router'

/**
 * 用 hash 路由：dist 由 FastAPI 挂在任意子路径也能跑（配合 vite base: './'）。
 */
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('./views/Home.vue'), meta: { title: '首页' } },
    { path: '/catalog', name: 'catalog', component: () => import('./views/Catalog.vue'), meta: { title: '全景目录' } },
    { path: '/algo/:key', name: 'algo', component: () => import('./views/AlgoDetail.vue'), meta: { title: '算法' } },
    { path: '/glossary', name: 'glossary', component: () => import('./views/Glossary.vue'), meta: { title: '术语表' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: (to) => (to.hash ? { el: to.hash, behavior: 'smooth', top: 70 } : { top: 0 }),
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? ''
  document.title = title ? `${title} · ML 3D 仿真台` : 'ML 3D 仿真台'
})
