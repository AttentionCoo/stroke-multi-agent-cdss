import axios from 'axios'
import { useUserStore } from '@/stores/user'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import router from '@/router'

NProgress.configure({ showSpinner: false })

const request = axios.create({
  baseURL: '/api',
  timeout: 600000,
})

// 添加请求拦截器
request.interceptors.request.use(
  function (config) {
    // 请求开始，开启进度条
    NProgress.start()

    // 携带token
    const userStore = useUserStore()
    const token = userStore.token
    if (userStore.hasToken) {
      config.headers.Authorization = token
      config.headers.token = token
    }

    return config
  },
  function (error) {
    NProgress.done()
    return Promise.reject(error)
  },
)

// 添加响应拦截器
request.interceptors.response.use(
  function (response) {
    NProgress.done()

    const { data } = response

    if (data.code === 1) {
      return data
    }

    return Promise.reject(data)
  },
  function (error) {
    // 响应错误，关闭进度条
    NProgress.done()

    // 处理 401 错误
    if (error.response && error.response.status === 401) {
      const userStore = useUserStore()
      userStore.reset()
      router.push('/login')
    }

    if (error.response?.data) {
      return Promise.reject(error.response.data)
    }

    return Promise.reject(error)
  },
)

export default request
