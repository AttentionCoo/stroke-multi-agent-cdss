<script setup>
import { nextTick, ref, watch } from 'vue'
import { globalSearchAPI } from '@/api/search'
import { showError } from '@/utils/feedback'

defineOptions({ name: 'GlobalSearchPalette' })

const props = defineProps({
  visible: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'navigate', 'command'])

const inputRef = ref(null)
const query = ref('')
const results = ref([])
const loading = ref(false)
let timer = null

const commands = [
  { key: 'new-chat', icon: '💬', title: '开始新的智能问诊', desc: '进入 AI 临床辅助分析' },
  { key: 'greenway', icon: '⏱️', title: '新建急诊绿道评估', desc: '记录卒中时间窗与风险检查' },
  { key: 'patients', icon: '👤', title: '打开患者管理', desc: '查找患者与随访时间线' },
  { key: 'reviews', icon: '🛡️', title: '打开医生复核中心', desc: '处理待批准或驳回的会诊' },
  { key: 'quality', icon: '📊', title: '打开质量与系统中心', desc: '查看 DNT、反馈与运行状态' },
  { key: 'calculator', icon: '🧮', title: '打开临床计算器', desc: 'rt-PA、GCS、mRS、CHA₂DS₂-VASc 等' },
]

function typeLabel(type) {
  return { patient: '患者', talk: '对话', knowledge: '资料' }[type] || '结果'
}

function typeIcon(type) {
  return { patient: '👤', talk: '💬', knowledge: '📚' }[type] || '•'
}

function close() {
  emit('close')
}

function runSearch() {
  clearTimeout(timer)
  const q = query.value.trim()
  if (!q) {
    results.value = []
    loading.value = false
    return
  }
  loading.value = true
  timer = setTimeout(async () => {
    try {
      const res = await globalSearchAPI(q)
      results.value = Array.isArray(res.data) ? res.data : []
    } catch (error) {
      showError(error?.msg || error?.message || '搜索失败')
      results.value = []
    } finally {
      loading.value = false
    }
  }, 220)
}

function navigate(result) {
  emit('navigate', result)
  close()
}

function runCommand(key) {
  emit('command', key)
  close()
}

function handleKeydown(event) {
  if (event.key === 'Escape') close()
}

watch(
  () => props.visible,
  async (visible) => {
    if (visible) {
      query.value = ''
      results.value = []
      await nextTick()
      inputRef.value?.focus()
    }
  },
)

watch(query, runSearch)
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="search-backdrop" @click.self="close" @keydown="handleKeydown">
      <section class="search-palette" aria-modal="true" role="dialog">
        <header class="search-header">
          <span class="search-icon">⌕</span>
          <input ref="inputRef" v-model="query" type="search" placeholder="搜索患者、对话、医学资料，或输入命令..." />
          <kbd>ESC</kbd>
        </header>

        <div class="search-body">
          <div v-if="loading" class="search-empty">正在搜索...</div>

          <template v-else-if="query.trim()">
            <div v-if="results.length" class="result-list">
              <button v-for="result in results" :key="`${result.type}-${result.id}`" type="button" class="result-item"
                @click="navigate(result)">
                <span class="result-icon">{{ typeIcon(result.type) }}</span>
                <span class="result-copy">
                  <strong>{{ result.title }}</strong>
                  <small>{{ result.subtitle }}</small>
                </span>
                <span class="result-type">{{ typeLabel(result.type) }}</span>
              </button>
            </div>
            <div v-else class="search-empty">没有找到匹配结果，试试更短的关键词。</div>
          </template>

          <template v-else>
            <p class="search-section-title">快捷命令</p>
            <div class="command-list">
              <button v-for="command in commands" :key="command.key" type="button" class="command-item"
                @click="runCommand(command.key)">
                <span class="command-icon">{{ command.icon }}</span>
                <span><strong>{{ command.title }}</strong><small>{{ command.desc }}</small></span>
                <span class="arrow">↗</span>
              </button>
            </div>
          </template>
        </div>

        <footer class="search-footer">
          <span>输入关键词即可搜索当前医生有权访问的数据</span>
          <span>Ctrl / ⌘ + K 打开</span>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.search-backdrop { position: fixed; inset: 0; z-index: 150; display: flex; justify-content: center; align-items: flex-start; padding: 10vh 18px 20px; background: rgba(15, 23, 42, .42); backdrop-filter: blur(5px); }
.search-palette { width: min(720px, 100%); max-height: 72vh; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--color-dialog-border); border-radius: 16px; background: var(--color-dialog-bg); box-shadow: 0 28px 80px rgba(15, 23, 42, .3); }
.search-header { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--color-border-item); }
.search-icon { color: var(--color-active-border); font-size: 23px; line-height: 1; }
.search-header input { flex: 1; min-width: 0; border: none; outline: none; background: transparent; color: var(--color-text-strong); font: inherit; font-size: 17px; }
.search-header kbd { border: 1px solid var(--color-border); border-radius: 5px; padding: 3px 6px; color: var(--color-text-weak); font-size: 10px; }
.search-body { flex: 1; overflow-y: auto; padding: 9px; }
.search-section-title { margin: 8px 10px; color: var(--color-text-weak); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.result-list, .command-list { display: flex; flex-direction: column; gap: 3px; }
.result-item, .command-item { display: flex; align-items: center; gap: 11px; width: 100%; border: 1px solid transparent; border-radius: 9px; background: transparent; padding: 10px 11px; text-align: left; cursor: pointer; color: var(--color-text-medium); }
.result-item:hover, .command-item:hover { background: var(--color-hover-bg); border-color: var(--color-border-item); }
.result-icon, .command-icon { flex: 0 0 31px; height: 31px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; background: var(--color-bg-light); font-size: 16px; }
.result-copy, .command-item > span:nth-child(2) { flex: 1; min-width: 0; }
.result-copy strong, .command-item strong { display: block; color: var(--color-text-strong); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-copy small, .command-item small { display: block; margin-top: 3px; color: var(--color-text-weak); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-type { color: var(--color-text-weak); font-size: 10px; }
.arrow { color: var(--color-text-weak); }
.search-empty { padding: 40px 16px; text-align: center; color: var(--color-text-weak); font-size: 12px; }
.search-footer { display: flex; justify-content: space-between; gap: 12px; padding: 9px 16px; border-top: 1px solid var(--color-border-item); color: var(--color-text-weak); font-size: 10px; }
@media (max-width: 600px) { .search-backdrop { padding-top: 5vh; } .search-footer { flex-direction: column; } }
</style>
