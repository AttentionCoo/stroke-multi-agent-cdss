import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPersistedstate from 'pinia-plugin-persistedstate'

import App from './App.vue'
import router from './router'

// 全局注册图标组件
import UserSVG from './components/svg/UserSVG.vue'
import PasswordSVG from './components/svg/PasswordSVG.vue'
import SendSVG from './components/svg/SendSVG.vue'

import 'normalize.css'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPersistedstate)

app.use(pinia)
app.use(router)

// 初始化主题
import { useThemeStore } from './stores/theme'
const themeStore = useThemeStore()
themeStore.applyTheme()

app.component('UserSVG', UserSVG)
app.component('PasswordSVG', PasswordSVG)
app.component('SendSVG', SendSVG)

app.mount('#app')
// PWA: 生产环境注册 Service Worker，支持安装到桌面/手机和静态资源缓存
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((error) => {
      console.warn('Service Worker 注册失败', error)
    })
  })
}
