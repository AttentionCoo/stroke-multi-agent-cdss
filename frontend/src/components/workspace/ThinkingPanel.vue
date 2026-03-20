<script setup>
import { ref, computed, watch } from 'vue'

defineOptions({ name: 'ThinkingPanel' })

const props = defineProps({
  // { events: [{step, title, content}, ...], elapsedSeconds: null|number, startTime: number }
  thinkingData: {
    type: Object,
    required: true,
  },
  // 是否仍在接收 thinking 事件（isThinking && 是最后一条消息）
  isStreaming: {
    type: Boolean,
    default: false,
  },
})

// 默认折叠；流结束时自动收起
const isExpanded = ref(false)

// 流结束后自动折叠
watch(
  () => props.isStreaming,
  (streaming) => {
    if (!streaming) isExpanded.value = false
  },
)

// streaming 时展开面板实时查看步骤
watch(
  () => props.isStreaming,
  (streaming) => {
    if (streaming) isExpanded.value = true
  },
  { immediate: true },
)

// 最新 thinking 步骤标题（streaming 时显示）
const latestTitle = computed(() => {
  const events = props.thinkingData?.events
  if (!events?.length) return 'AI 思考中...'
  const last = events[events.length - 1]
  return last.title || last.step || 'AI 思考中...'
})

// 头部文字
const headerText = computed(() => {
  if (props.isStreaming) return latestTitle.value
  const secs = props.thinkingData?.elapsedSeconds
  if (secs != null) return `已深度思考（用时 ${secs} 秒）`
  return '已深度思考'
})

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

// 尝试将 content 解析为 JSON，格式化展示
function formatContent(content) {
  if (!content) return null
  if (typeof content !== 'string') return String(content)
  const trimmed = content.trim()
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed)
      return { type: 'json', data: parsed }
    } catch {
      // 不是合法 JSON，按普通文本处理
    }
  }
  // 截断超长文字
  if (trimmed.length > 500) return { type: 'text', data: trimmed.slice(0, 500) + '…' }
  return { type: 'text', data: trimmed }
}
</script>

<template>
  <div class="thinking-panel" :class="{ streaming: isStreaming }">
    <!-- 头部：点击折叠/展开 -->
    <div class="thinking-header" @click="toggleExpand">
      <div class="thinking-header-left">
        <!-- streaming 时显示弹跳点动画 -->
        <span v-if="isStreaming" class="thinking-dots">
          <span></span><span></span><span></span>
        </span>
        <!-- 完成后显示脑图标 -->
        <span v-else class="thinking-icon">🧠</span>
        <span class="thinking-header-text">{{ headerText }}</span>
      </div>
      <!-- 非 streaming 时显示折叠箭头 -->
      <span v-if="!isStreaming" class="thinking-toggle-icon" :class="{ expanded: isExpanded }">▾</span>
    </div>

    <!-- 步骤列表 -->
    <div class="thinking-body" :class="{ expanded: isExpanded }">
      <div
        v-for="(event, idx) in thinkingData.events"
        :key="idx"
        class="thinking-step"
      >
        <div class="step-title">
          <span class="step-index">{{ idx + 1 }}</span>
          {{ event.title || event.step }}
        </div>
        <template v-if="formatContent(event.content)">
          <!-- JSON 格式：key-value 列表 -->
          <div
            v-if="formatContent(event.content).type === 'json'"
            class="step-content step-content-json"
          >
            <div
              v-for="(val, key) in formatContent(event.content).data"
              :key="key"
              class="json-row"
            >
              <span class="json-key">{{ key }}</span>
              <span class="json-val">{{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
            </div>
          </div>
          <!-- 普通文本 -->
          <div v-else class="step-content">
            {{ formatContent(event.content).data }}
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.thinking-panel {
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 8px;
  margin-bottom: 10px;
  background: var(--color-bg-subtle, #f9fafb);
  overflow: hidden;

  // streaming 时左侧闪烁边框
  &.streaming {
    border-left: 3px solid var(--color-primary, #11967f);
    animation: thinking-border-pulse 2s ease-in-out infinite;
  }
}

@keyframes thinking-border-pulse {
  0%, 100% { border-left-color: var(--color-primary, #11967f); }
  50% { border-left-color: rgba(17, 150, 127, 0.35); }
}

.thinking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  cursor: pointer;
  user-select: none;
  gap: 8px;
}

.thinking-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.thinking-header-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-medium);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thinking-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.thinking-toggle-icon {
  font-size: 14px;
  color: var(--color-text-weak);
  flex-shrink: 0;
  transition: transform 0.2s ease;
  display: inline-block;

  &.expanded {
    transform: rotate(180deg);
  }
}

/* 弹跳点（与 ChatWorkspace 样式一致） */
.thinking-dots {
  display: flex;
  gap: 4px;
  flex-shrink: 0;

  span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-primary, #11967f);
    animation: thinking-bounce 1.4s ease-in-out infinite both;

    &:nth-child(2) { animation-delay: 0.22s; }
    &:nth-child(3) { animation-delay: 0.44s; }
  }
}

@keyframes thinking-bounce {
  0%, 80%, 100% { transform: scale(0.55); opacity: 0.35; }
  40% { transform: scale(1); opacity: 1; }
}

/* 折叠体：max-height 过渡 */
.thinking-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;

  &.expanded {
    max-height: 2000px;
  }
}

.thinking-step {
  padding: 8px 12px;
  border-top: 1px solid var(--color-border, #e5e7eb);
}

.step-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-primary-dark, #0d7a68);
  display: flex;
  align-items: center;
  gap: 6px;
}

.step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(17, 150, 127, 0.12);
  color: var(--color-primary-dark, #0d7a68);
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.step-content {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-medium);
  line-height: 1.5;
  word-break: break-word;
}

.step-content-json {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.json-row {
  display: flex;
  gap: 6px;
  font-size: 12px;
}

.json-key {
  color: var(--color-primary-dark, #0d7a68);
  font-weight: 500;
  flex-shrink: 0;

  &::after { content: ':'; }
}

.json-val {
  color: var(--color-text-medium);
  word-break: break-all;
}
</style>
