<script setup>
import { ref, computed, watch } from 'vue'
import { stripThinkingMarkdown } from '@/utils/thinkingEvents'
import { copyText } from '@/utils/clipboard'

defineOptions({ name: 'ThinkingPanel' })

const props = defineProps({
  // 思考记录包含事件列表、耗时和开始时间。
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

// 默认展开（"全部打印"思考链）
const isExpanded = ref(true)

// 复制反馈状态
const copiedAll = ref(false)
const copiedSteps = ref({})

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
  if (!events?.length) return 'AI 分析中...'
  const last = events[events.length - 1]
  return last.title || last.step || 'AI 分析中...'
})

// 头部文字
const headerText = computed(() => {
  if (props.isStreaming) return latestTitle.value
  const secs = props.thinkingData?.elapsedSeconds
  if (secs != null) return `临床分析已完成（用时 ${secs} 秒）`
  return '临床分析已完成'
})

// LLM 用量信息(来自 done 事件): token 数 / 调用次数 / 估算成本
const usageText = computed(() => {
  const usage = props.thinkingData?.usage
  if (!usage) return ''
  const parts = []
  if (usage.input_tokens != null) parts.push(`${usage.input_tokens} 入 / ${usage.output_tokens} 出 tokens`)
  if (usage.calls != null) parts.push(`${usage.calls} 次 LLM 调用`)
  if (usage.cost != null) parts.push(`估算成本 ¥${usage.cost}`)
  return parts.join(' · ')
})

// ── 会诊过程时间轴 ─────────────────────────────────────────
const EXPERT_STEPS = new Set(['reason', 'debate', 'consensus_agent'])
const FINAL_STEPS = new Set(['validate', 'generate_report', 'knowledge_answer', 'reject'])

function phaseOf(step) {
  if (EXPERT_STEPS.has(step)) return 'experts'
  if (FINAL_STEPS.has(step)) return 'final'
  return 'outer'
}

const timelineRows = computed(() => {
  const events = props.thinkingData?.events || []
  const now = Date.now()
  const rows = events
    .filter((e) => e.startedAt)
    .map((e) => {
      const end = e.endedAt || e.updatedAt || now
      const duration = Math.max(0.1, (end - e.startedAt) / 1000)
      return {
        step: e.step,
        title: e.title || e.step,
        startedAt: e.startedAt,
        seconds: Math.round(duration * 10) / 10,
        duration,
        phase: phaseOf(e.step),
      }
    })
  if (!rows.length) return []
  const total = Math.max(...rows.map((r) => r.duration), 0.1)
  return rows.map((r) => ({ ...r, width: Math.max(2, Math.round((r.duration / total) * 1000) / 10) }))
})

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

// 尝试将 content 解析为 JSON，格式化展示
function formatContent(content) {
  if (!content) return null
  const trimmed = stripThinkingMarkdown(content)
  if (!trimmed) return null
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed)
      return { type: 'json', data: parsed }
    } catch {
      // 不是合法 JSON，按普通文本处理
    }
  }
  // 思考链全文完整展示（不截断）
  return { type: 'text', data: trimmed }
}

// 单个步骤的纯文本(标题 + 内容), 用于复制
function buildStepText(event, idx) {
  const title = event.title || event.step || `步骤${idx + 1}`
  const content = stripThinkingMarkdown(event.content || '')
  return `【${title}】\n${content}`.trim()
}

// 复制单个步骤
async function copyStep(event, idx) {
  const ok = await copyText(buildStepText(event, idx))
  if (ok) {
    copiedSteps.value[idx] = true
    setTimeout(() => {
      copiedSteps.value[idx] = false
    }, 1500)
  }
}

// 复制整条思考链
async function copyAll() {
  const events = props.thinkingData?.events || []
  if (!events.length) return
  const text = events.map((e, i) => buildStepText(e, i)).join('\n\n')
  const ok = await copyText(text)
  if (ok) {
    copiedAll.value = true
    setTimeout(() => {
      copiedAll.value = false
    }, 1500)
  }
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
        <span v-else class="thinking-icon">✓</span>
        <span class="thinking-header-text">{{ headerText }}</span>
        <span v-if="usageText" class="usage-badge" title="LLM 用量统计">{{ usageText }}</span>
      </div>
      <div class="thinking-header-actions">
        <button type="button" class="copy-all-btn" :class="{ copied: copiedAll }" @click.stop="copyAll">
          {{ copiedAll ? '已复制' : '复制全部' }}
        </button>
        <!-- 非 streaming 时显示折叠箭头 -->
        <span v-if="!isStreaming" class="thinking-toggle-icon" :class="{ expanded: isExpanded }">▾</span>
      </div>
    </div>

    <!-- 步骤列表 -->
    <div class="thinking-body" :class="{ expanded: isExpanded }">
      <!-- 会诊过程时间轴 -->
      <div v-if="timelineRows.length" class="timeline">
        <div class="timeline-title">
          ⏱ 会诊过程时间轴
          <span class="timeline-legend">
            <span class="legend-dot outer"></span>流程
            <span class="legend-dot experts"></span>专家会诊
            <span class="legend-dot final"></span>校验报告
          </span>
        </div>
        <div v-for="row in timelineRows" :key="`${row.step}-${row.startedAt}`" class="timeline-row">
          <span class="timeline-label" :title="row.title">{{ row.title }}</span>
          <div class="timeline-track">
            <div class="timeline-bar" :class="`phase-${row.phase}`" :style="{ width: row.width + '%' }">
              <span v-if="row.width > 14" class="timeline-duration">{{ row.seconds }}s</span>
            </div>
          </div>
        </div>
      </div>

      <div
        v-for="(event, idx) in thinkingData.events"
        :key="idx"
        class="thinking-step"
        :class="{ completed: event.status === 'done' }"
      >
        <div class="step-title">
          <span class="step-index">{{ idx + 1 }}</span>
          <span class="step-name">{{ event.title || event.step }}</span>
          <button
            v-if="event.status === 'done' && event.content"
            type="button"
            class="step-copy-btn"
            :class="{ copied: copiedSteps[idx] }"
            :title="copiedSteps[idx] ? '已复制' : '复制本步骤内容'"
            @click="copyStep(event, idx)"
          >
            {{ copiedSteps[idx] ? '✓' : '复制' }}
          </button>
          <span v-if="event.status === 'done'" class="step-status" title="已完成">✓</span>
          <span v-else class="step-status running" title="处理中"></span>
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

.usage-badge {
  font-size: 11px;
  color: var(--color-text-weak, #9ca3af);
  background: rgba(17, 150, 127, 0.06);
  border-radius: 10px;
  padding: 1px 8px;
  white-space: nowrap;
  flex-shrink: 0;
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

.thinking-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.copy-all-btn {
  border: 1px solid var(--color-border, #e5e7eb);
  background: var(--color-bg-light, #ffffff);
  color: var(--color-primary-dark, #0d7a68);
  font-size: 12px;
  line-height: 1;
  padding: 4px 10px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    border-color: var(--color-primary, #11967f);
    background: rgba(17, 150, 127, 0.06);
  }

  &.copied {
    border-color: var(--color-primary, #11967f);
    background: var(--color-primary, #11967f);
    color: #ffffff;
  }
}

.step-copy-btn {
  border: none;
  background: transparent;
  color: var(--color-text-weak, #9ca3af);
  font-size: 11px;
  line-height: 1;
  padding: 2px 8px;
  margin-left: 6px;
  border-radius: 10px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;

  &:hover {
    color: var(--color-primary, #11967f);
    background: rgba(17, 150, 127, 0.08);
  }

  &.copied {
    color: var(--color-primary, #11967f);
    font-weight: 600;
  }
}

/* ── 会诊过程时间轴 ── */
.timeline {
  padding: 10px 12px 4px;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.timeline-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary-dark, #0d7a68);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.timeline-legend {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-weak, #9ca3af);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  display: inline-block;

  &.outer { background: #11967f; }
  &.experts { background: #f59e0b; }
  &.final { background: #8b5cf6; }
}

.timeline-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}

.timeline-label {
  width: 118px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-text-medium);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: right;
}

.timeline-track {
  flex: 1;
  background: rgba(17, 150, 127, 0.06);
  border-radius: 4px;
  height: 16px;
  overflow: hidden;
}

.timeline-bar {
  height: 100%;
  border-radius: 4px;
  display: flex;
  align-items: center;
  padding-left: 6px;
  transition: width 0.3s ease;

  &.phase-outer { background: linear-gradient(90deg, #11967f, #34c2a8); }
  &.phase-experts { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
  &.phase-final { background: linear-gradient(90deg, #8b5cf6, #a78bfa); }
}

.timeline-duration {
  font-size: 10px;
  color: #ffffff;
  white-space: nowrap;
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

/* 折叠体：展开后不限高, 思考链全文(专家意见/证据全文)完整可见 */
.thinking-body {
  max-height: 0;
  overflow: hidden;

  &.expanded {
    max-height: none;
    overflow: visible;
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

.step-name {
  min-width: 0;
  flex: 1;
  overflow-wrap: anywhere;
}

.step-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-left: auto;
  color: var(--color-primary-dark, #0d7a68);
  font-size: 12px;
  flex-shrink: 0;

  &.running {
    width: 12px;
    height: 12px;
    margin-right: 3px;
    border: 2px solid rgba(17, 150, 127, 0.25);
    border-top-color: var(--color-primary, #11967f);
    border-radius: 50%;
    animation: thinking-spin 0.8s linear infinite;
  }
}

@keyframes thinking-spin {
  to { transform: rotate(360deg); }
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
  // 思考链全文多行打印: 保留换行与缩进
  white-space: pre-wrap;
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
