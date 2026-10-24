<script setup>
import { ref, watch } from 'vue'
import { getDashboardSummaryAPI } from '@/api/dashboard'
import { showError } from '@/utils/feedback'

defineOptions({ name: 'NotificationCenter' })

const props = defineProps({ visible: { type: Boolean, default: false } })
const emit = defineEmits(['close', 'navigate', 'updated'])
const items = ref([])
const loading = ref(false)
const readIds = ref(loadReadIds())

function loadReadIds() {
  try {
    return new Set(JSON.parse(localStorage.getItem('stroke_notification_read') || '[]'))
  } catch {
    return new Set()
  }
}

function persistReadIds() {
  try {
    localStorage.setItem('stroke_notification_read', JSON.stringify([...readIds.value]))
  } catch {
    // 忽略
  }
}

function notificationKey(item, index) {
  return `${item.type}-${item.taskId || item.followupId || item.patientId || index}-${item.time || ''}`
}

function isUnread(item, index) {
  return !readIds.value.has(notificationKey(item, index))
}

function markAllRead() {
  items.value.forEach((item, index) => readIds.value.add(notificationKey(item, index)))
  persistReadIds()
  emit('updated')
}

function openItem(item, index) {
  readIds.value.add(notificationKey(item, index))
  persistReadIds()
  emit('navigate', item)
  emit('updated')
  emit('close')
}

async function load() {
  loading.value = true
  try {
    const res = await getDashboardSummaryAPI()
    items.value = res.data?.notifications || []
    emit('updated')
  } catch (error) {
    showError(error?.msg || error?.message || '通知加载失败')
  } finally {
    loading.value = false
  }
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

watch(() => props.visible, (visible) => { if (visible) load() }, { immediate: true })
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="notification-backdrop" @click.self="emit('close')">
      <section class="notification-panel">
        <header>
          <div><p class="eyebrow">INBOX</p><h3>通知中心</h3></div>
          <button type="button" class="text-btn" @click="markAllRead">全部已读</button>
        </header>
        <div v-if="loading" class="empty">正在加载通知...</div>
        <div v-else-if="items.length" class="notification-list">
          <button v-for="(item, index) in items" :key="notificationKey(item, index)" type="button"
            class="notification-item" :class="{ unread: isUnread(item, index), danger: item.severity === 'danger' }"
            @click="openItem(item, index)">
            <span class="notification-dot"></span>
            <span class="notification-copy">
              <strong>{{ item.title }}</strong>
              <small>{{ item.message }}</small>
            </span>
            <span class="notification-time">{{ formatTime(item.time) }}</span>
          </button>
        </div>
        <div v-else class="empty">暂无待办与提醒。</div>
        <footer>通知由待复核、随访到期和系统任务实时聚合。</footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.notification-backdrop { position: fixed; inset: 0; z-index: 140; background: rgba(15, 23, 42, .26); }
.notification-panel { position: absolute; top: 68px; right: 24px; width: min(410px, calc(100vw - 24px)); max-height: 70vh; display: flex; flex-direction: column; border: 1px solid var(--color-dialog-border); border-radius: 14px; background: var(--color-dialog-bg); box-shadow: var(--shadow-dialog); overflow: hidden; }
.notification-panel header { display: flex; justify-content: space-between; align-items: flex-start; padding: 16px; border-bottom: 1px solid var(--color-border-item); }
.eyebrow { margin: 0 0 5px; color: var(--color-active-border); font-size: 9px; font-weight: 800; letter-spacing: .16em; }
.notification-panel h3 { margin: 0; color: var(--color-text-strong); font-size: 17px; }
.text-btn { border: none; background: transparent; color: var(--color-active-border); font-size: 11px; cursor: pointer; }
.notification-list { overflow-y: auto; padding: 6px; }
.notification-item { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; gap: 10px; align-items: center; width: 100%; padding: 11px; border: none; border-radius: 9px; background: transparent; text-align: left; cursor: pointer; }
.notification-item:hover { background: var(--color-hover-bg); }
.notification-dot { width: 7px; height: 7px; border-radius: 50%; background: transparent; }
.notification-item.unread .notification-dot { background: var(--color-active-border); }
.notification-item.danger .notification-dot { background: var(--color-red); }
.notification-copy strong { display: block; color: var(--color-text-strong); font-size: 12px; }
.notification-copy small { display: block; margin-top: 3px; color: var(--color-text-medium); font-size: 11px; line-height: 1.45; }
.notification-time { color: var(--color-text-weak); font-size: 9px; white-space: nowrap; }
.empty { padding: 42px 16px; text-align: center; color: var(--color-text-weak); font-size: 12px; }
.notification-panel footer { padding: 10px 14px; border-top: 1px solid var(--color-border-item); color: var(--color-text-weak); font-size: 10px; }
</style>
