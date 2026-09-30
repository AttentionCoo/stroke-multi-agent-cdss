<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { feedbackState, removeToast, settleConfirm } from '@/utils/feedback'

defineOptions({ name: 'FeedbackHost' })

const TOAST_ICONS = {
  success: '✓',
  error: '✕',
  warning: '!',
  info: 'i',
}

function handleKeydown(event) {
  if (event.key !== 'Escape') return
  if (feedbackState.confirm.visible) settleConfirm(false)
}

function handleConfirm() {
  settleConfirm(true)
}

function handleCancel() {
  settleConfirm(false)
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <!-- Toast 轻提示栈：顶部居中，不拦截任何操作 -->
    <div class="toast-stack" role="status" aria-live="polite">
      <transition-group name="fade-slide">
        <div v-for="toast in feedbackState.toasts" :key="toast.id" class="toast"
          :class="`toast--${toast.type}`" @click="removeToast(toast.id)">
          <span class="toast-icon">{{ TOAST_ICONS[toast.type] || 'i' }}</span>
          <span class="toast-message">{{ toast.message }}</span>
        </div>
      </transition-group>
    </div>

    <!-- Promise 化确认框：复用全局 .dialog-overlay/.dialog-card 样式 -->
    <transition name="fade">
      <div v-if="feedbackState.confirm.visible" class="dialog-overlay confirm-overlay"
        @click.self="handleCancel">
        <div class="dialog-card confirm-dialog" role="dialog" aria-modal="true">
          <div class="dialog-head">
            <div>
              <p class="summary-label">确认操作</p>
              <h3>{{ feedbackState.confirm.title }}</h3>
            </div>
            <button type="button" class="ghost-icon" aria-label="关闭"
              @click="handleCancel">✕</button>
          </div>

          <p class="confirm-message">{{ feedbackState.confirm.message }}</p>

          <div class="dialog-footer">
            <button type="button" class="secondary-action" @click="handleCancel">
              {{ feedbackState.confirm.cancelText }}
            </button>
            <button type="button" class="primary-action"
              :class="{ danger: feedbackState.confirm.danger }" @click="handleConfirm">
              {{ feedbackState.confirm.confirmText }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped lang="scss">
/* ── Toast 栈 ── */
.toast-stack {
  position: fixed;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1200;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  pointer-events: none; // 栈容器不拦截点击, 单条 toast 自身可点击关闭
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: min(560px, 86vw);
  padding: 10px 16px;
  border-radius: var(--radius-lg);
  background: var(--color-dialog-bg);
  border: 1px solid var(--color-dialog-border);
  box-shadow: var(--shadow-menu);
  font-size: 14px;
  color: var(--color-text-strong);
  pointer-events: auto;
  cursor: pointer;
  transition: border-color var(--transition-fast);

  &:hover {
    border-color: var(--color-border);
  }
}

.toast-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 800;
  color: #fff;
  flex-shrink: 0;
}

.toast-message {
  line-height: 1.5;
  word-break: break-word;
}

.toast--success .toast-icon {
  background: var(--color-primary);
}

.toast--error .toast-icon {
  background: var(--color-red);
}

.toast--warning .toast-icon {
  background: var(--color-orange);
}

.toast--info .toast-icon {
  background: var(--color-text-weak);
}

/* ── 确认框 ── */
.confirm-overlay {
  z-index: 1200;
}

.confirm-dialog {
  width: min(420px, 92vw);
  padding: 20px 22px;
}

.confirm-message {
  margin: 14px 0 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-medium);
  word-break: break-word;
}

.primary-action.danger {
  background: var(--color-red);
}
</style>
