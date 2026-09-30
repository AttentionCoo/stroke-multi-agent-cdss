import { reactive } from 'vue'

// ── 全局反馈单例：Toast 轻提示 + Promise 化确认框 ─────────────────
// 替代浏览器原生 alert/confirm：原生弹窗样式无法定制、深色模式下刺眼、
// 且会阻塞页面渲染。宿主组件 FeedbackHost 挂载在 App.vue 中。
// 注意：confirm 同一时刻只允许一个，重复调用直接 resolve(false)。

export const feedbackState = reactive({
  toasts: [],
  confirm: {
    visible: false,
    title: '',
    message: '',
    confirmText: '确认',
    cancelText: '取消',
    danger: false,
    resolve: null,
  },
})

let toastSeq = 0

export function removeToast(id) {
  const index = feedbackState.toasts.findIndex((toast) => toast.id === id)
  if (index !== -1) feedbackState.toasts.splice(index, 1)
}

export function showToast(message, type = 'info', duration = 3000) {
  const id = ++toastSeq
  feedbackState.toasts.push({ id, type, message })
  setTimeout(() => removeToast(id), duration)
}

export const showSuccess = (message) => showToast(message, 'success')
export const showError = (message) => showToast(message, 'error')
export const showWarning = (message) => showToast(message, 'warning')
export const showInfo = (message) => showToast(message, 'info')

export function showConfirm(options = {}) {
  const {
    title = '确认操作',
    message = '',
    confirmText = '确认',
    cancelText = '取消',
    danger = false,
  } = options

  // 已有确认框在等待用户操作：直接返回 false，避免堆叠
  if (feedbackState.confirm.visible) return Promise.resolve(false)

  return new Promise((resolve) => {
    Object.assign(feedbackState.confirm, {
      visible: true,
      title,
      message,
      confirmText,
      cancelText,
      danger,
      resolve,
    })
  })
}

// 确认框关闭（确认或取消），由 FeedbackHost 调用
export function settleConfirm(result) {
  const { resolve } = feedbackState.confirm
  if (!resolve) return
  feedbackState.confirm.visible = false
  feedbackState.confirm.resolve = null
  resolve(result)
}
