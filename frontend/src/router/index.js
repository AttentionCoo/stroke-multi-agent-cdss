import { createRouter, createWebHistory } from 'vue-router'
import login from '@/views/login.vue'
import talk from '@/views/talk.vue'

import { useUserStore } from '@/stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: login },
    { path: '/', component: talk },
  ],
})
// 全局前置守卫
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  if (to.path === '/' && !userStore.hasToken) {
    next('/login')
    // next()
  } else if (to.path === '/login' && userStore.hasToken) {
    next()
  } else {
    next()
  }
})

export default router
