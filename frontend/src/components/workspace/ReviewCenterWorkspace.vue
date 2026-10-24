<script setup>
import { computed, onMounted, ref } from 'vue'
import { getPendingReviewsAPI } from '@/api/reviews'
import { resumeClinicalReviewStreamAPI } from '@/api/talk'
import { copyText } from '@/utils/clipboard'
import { showError, showSuccess, showWarning } from '@/utils/feedback'

defineOptions({ name: 'ReviewCenterWorkspace' })

const emit = defineEmits(['updated'])

const tasks = ref([])
const loading = ref(false)
const selectedId = ref(null)
const feedbackDrafts = ref({})
const processingId = ref(null)
const reportPreview = ref(null)

const selectedTask = computed(() => tasks.value.find((task) => task.taskId === selectedId.value) || tasks.value[0] || null)
const pendingCount = computed(() => tasks.value.length)

function formatDateTime(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function selectTask(task) {
  selectedId.value = task.taskId
}

function feedbackOf(taskId) {
  return feedbackDrafts.value[taskId] || ''
}

function setFeedback(taskId, value) {
  feedbackDrafts.value = { ...feedbackDrafts.value, [taskId]: value }
}

function payloadOf(task) {
  return task?.payload || {}
}

async function load() {
  loading.value = true
  try {
    const res = await getPendingReviewsAPI(30)
    tasks.value = Array.isArray(res.data) ? res.data : []
    if (!tasks.value.some((task) => task.taskId === selectedId.value)) {
      selectedId.value = tasks.value[0]?.taskId || null
    }
  } catch (error) {
    showError(error?.msg || error?.message || '待复核任务加载失败')
  } finally {
    loading.value = false
    emit('updated')
  }
}

async function decide(task, approved) {
  if (!task?.taskId || processingId.value) return
  const feedback = feedbackOf(task.taskId).trim()
  if (!approved && !feedback) {
    showWarning('驳回会诊时必须填写修改意见')
    return
  }
  processingId.value = task.taskId
  let answer = ''
  let nextReview = null
  try {
    await resumeClinicalReviewStreamAPI(
      task.taskId,
      { approved, feedback },
      (chunk) => { answer += chunk },
      () => {},
      () => {},
      (review) => { nextReview = review },
    )
    if (nextReview) {
      showWarning('已按医生意见重新会诊，新的结论仍需复核')
    } else {
      reportPreview.value = {
        title: approved ? '会诊报告已生成' : '会诊报告已更新',
        content: answer || '模型未返回可展示的文本，请在原对话中查看完整报告。',
      }
      showSuccess(approved ? '复核通过，报告已生成并保存' : '驳回意见已送交专家重新会诊')
    }
    await load()
  } catch (error) {
    showError(error?.msg || error?.message || '复核处理失败')
  } finally {
    processingId.value = null
  }
}

async function copyPreview() {
  if (!reportPreview.value?.content) return
  await copyText(reportPreview.value.content)
  showSuccess('报告已复制')
}

onMounted(load)
</script>

<template>
  <section class="review-center">
    <header class="review-header">
      <div>
        <p class="eyebrow">HUMAN-IN-THE-LOOP</p>
        <h2>医生复核中心</h2>
        <p>集中处理 AI 会诊结论。批准后生成最终报告，驳回后携带意见重新会诊。</p>
      </div>
      <div class="header-actions">
        <span class="pending-pill">待复核 {{ pendingCount }}</span>
        <button type="button" class="secondary-action" :disabled="loading" @click="load">{{ loading ? '刷新中...' : '刷新' }}</button>
      </div>
    </header>

    <div v-if="loading && !tasks.length" class="empty-state">正在加载待复核任务...</div>
    <div v-else-if="!tasks.length" class="empty-state">
      <strong>没有待复核会诊</strong>
      <p>当 AI 会诊在报告生成前挂起时，任务会自动出现在这里。</p>
    </div>

    <div v-else class="review-layout">
      <aside class="task-list">
        <button v-for="task in tasks" :key="task.taskId" type="button" class="task-item"
          :class="{ active: selectedTask?.taskId === task.taskId }" @click="selectTask(task)">
          <span class="task-id">#{{ task.taskId }}</span>
          <strong>{{ task.payload?.title || '会诊结论待复核' }}</strong>
          <small>{{ formatDateTime(task.updatedAt) }} · {{ task.threadId?.slice(0, 10) }}...</small>
        </button>
      </aside>

      <main v-if="selectedTask" class="review-detail">
        <div class="detail-head">
          <div>
            <p class="eyebrow">REVIEW TASK #{{ selectedTask.taskId }}</p>
            <h3>{{ payloadOf(selectedTask).title || '会诊结论待医生复核' }}</h3>
            <small>对话 ID：{{ selectedTask.talkId }} · 线程：{{ selectedTask.threadId }}</small>
          </div>
          <span class="status-chip">PENDING</span>
        </div>

        <section v-if="payloadOf(selectedTask).consensus" class="review-section">
          <h4>专家共识</h4>
          <p>{{ payloadOf(selectedTask).consensus }}</p>
        </section>
        <section v-if="payloadOf(selectedTask).proposal" class="review-section">
          <h4>综合提案</h4>
          <p>{{ payloadOf(selectedTask).proposal }}</p>
        </section>
        <section v-if="payloadOf(selectedTask).key_risks?.length" class="review-section risk">
          <h4>关键风险</h4>
          <ul><li v-for="(risk, index) in payloadOf(selectedTask).key_risks" :key="index">{{ risk }}</li></ul>
        </section>

        <section class="decision-section">
          <label for="review-feedback">复核意见</label>
          <textarea id="review-feedback" :value="feedbackOf(selectedTask.taskId)" rows="4"
            placeholder="驳回时必须填写具体修改意见；批准时可以留空。"
            @input="setFeedback(selectedTask.taskId, $event.target.value)"></textarea>
          <div class="decision-actions">
            <button type="button" class="reject-btn" :disabled="processingId === selectedTask.taskId"
              @click="decide(selectedTask, false)">{{ processingId === selectedTask.taskId ? '处理中...' : '驳回并重新会诊' }}</button>
            <button type="button" class="approve-btn" :disabled="processingId === selectedTask.taskId"
              @click="decide(selectedTask, true)">{{ processingId === selectedTask.taskId ? '处理中...' : '批准并生成报告' }}</button>
          </div>
        </section>
      </main>
    </div>

    <Teleport to="body">
      <div v-if="reportPreview" class="preview-backdrop" @click.self="reportPreview = null">
        <div class="preview-modal">
          <header><div><p class="eyebrow">REPORT RESULT</p><h3>{{ reportPreview.title }}</h3></div><button type="button" class="close-btn" @click="reportPreview = null">×</button></header>
          <pre>{{ reportPreview.content }}</pre>
          <footer><button type="button" class="secondary-action" @click="copyPreview">复制全文</button><button type="button" class="primary-action" @click="reportPreview = null">关闭</button></footer>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped lang="scss">
.review-center { height: 100%; min-height: 0; overflow: hidden; display: flex; flex-direction: column; background: var(--color-bg-base); }
.review-header { display: flex; justify-content: space-between; gap: 20px; align-items: flex-end; padding: 22px 24px 16px; border-bottom: 1px solid var(--color-border); }
.eyebrow { margin: 0 0 7px; color: var(--color-active-border); font-size: 10px; font-weight: 800; letter-spacing: .16em; }
.review-header h2 { margin: 0; color: var(--color-text-strong); font-size: 23px; }
.review-header p { margin: 7px 0 0; color: var(--color-text-medium); font-size: 12px; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.pending-pill { border-radius: 999px; padding: 6px 11px; background: var(--color-badge-accent-bg); color: var(--color-orange); font-size: 12px; font-weight: 800; }
.review-layout { flex: 1; min-height: 0; display: grid; grid-template-columns: 300px minmax(0, 1fr); }
.task-list { overflow-y: auto; border-right: 1px solid var(--color-border); background: var(--color-bg-light); padding: 8px; }
.task-item { width: 100%; border: 1px solid transparent; border-radius: 10px; padding: 12px; margin-bottom: 7px; text-align: left; background: transparent; cursor: pointer; color: var(--color-text-medium); }
.task-item:hover { background: var(--color-hover-bg); }
.task-item.active { background: var(--color-active-bg); border-color: var(--color-active-border); }
.task-item .task-id { display: block; margin-bottom: 5px; color: var(--color-active-border); font-size: 10px; font-weight: 800; }
.task-item strong { display: block; color: var(--color-text-strong); font-size: 13px; }
.task-item small { display: block; margin-top: 5px; color: var(--color-text-weak); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.review-detail { overflow-y: auto; padding: 22px 26px; }
.detail-head { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; padding-bottom: 14px; border-bottom: 1px solid var(--color-border-item); }
.detail-head h3 { margin: 0; color: var(--color-text-strong); font-size: 20px; }
.detail-head small { display: block; margin-top: 6px; color: var(--color-text-weak); font-size: 11px; }
.status-chip { border-radius: 999px; padding: 5px 10px; background: var(--color-badge-accent-bg); color: var(--color-orange); font-size: 11px; font-weight: 800; }
.review-section { margin-top: 14px; padding: 15px; border-radius: 11px; border: 1px solid var(--color-border-item); background: var(--color-bg-light); }
.review-section h4 { margin: 0 0 8px; color: var(--color-text-label); font-size: 13px; }
.review-section p, .review-section li { margin: 0; color: var(--color-text-medium); font-size: 13px; line-height: 1.75; white-space: pre-wrap; }
.review-section ul { margin: 0; padding-left: 20px; }
.review-section.risk { border-left: 3px solid var(--color-orange); }
.decision-section { margin-top: 18px; padding: 16px; border-radius: 12px; border: 1px solid var(--color-border); background: var(--color-bg-base); }
.decision-section label { display: block; margin-bottom: 8px; color: var(--color-text-strong); font-size: 13px; font-weight: 700; }
.decision-section textarea { width: 100%; box-sizing: border-box; min-height: 110px; resize: vertical; border: 1px solid var(--color-border); border-radius: 8px; padding: 10px 12px; background: var(--color-bg-input); color: var(--color-text-strong); font: inherit; font-size: 13px; }
.decision-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 12px; }
.reject-btn, .approve-btn { border-radius: 8px; padding: 9px 14px; font-size: 12px; font-weight: 800; cursor: pointer; }
.reject-btn { border: 1px solid var(--color-border); background: var(--color-bg-base); color: var(--color-text-medium); }
.approve-btn { border: 1px solid var(--color-active-border); background: var(--color-active-border); color: #fff; }
.reject-btn:disabled, .approve-btn:disabled { opacity: .5; cursor: not-allowed; }
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: var(--color-text-weak); font-size: 13px; }
.empty-state strong { color: var(--color-text-strong); font-size: 17px; }
.empty-state p { margin: 0; font-size: 12px; }
.preview-backdrop { position: fixed; inset: 0; z-index: 120; display: flex; align-items: center; justify-content: center; background: var(--color-overlay-bg); padding: 24px; }
.preview-modal { width: min(900px, 100%); max-height: 86vh; display: flex; flex-direction: column; border: 1px solid var(--color-dialog-border); border-radius: 16px; background: var(--color-dialog-bg); box-shadow: var(--shadow-dialog); }
.preview-modal header { display: flex; justify-content: space-between; gap: 16px; padding: 18px 20px; border-bottom: 1px solid var(--color-border-item); }
.preview-modal h3 { margin: 0; color: var(--color-text-strong); font-size: 18px; }
.preview-modal pre { flex: 1; overflow: auto; margin: 0; padding: 18px 20px; white-space: pre-wrap; word-break: break-word; color: var(--color-text-strong); font-family: inherit; font-size: 13px; line-height: 1.75; }
.preview-modal footer { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--color-border-item); }
.close-btn { border: none; background: transparent; color: var(--color-text-medium); font-size: 24px; cursor: pointer; }
@media (max-width: 800px) { .review-layout { grid-template-columns: 1fr; } .task-list { max-height: 180px; border-right: none; border-bottom: 1px solid var(--color-border); } .review-header { flex-direction: column; align-items: flex-start; } }
</style>
