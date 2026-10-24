<script setup>
import { ref, watch } from 'vue'
import {
  completePatientFollowupAPI,
  createPatientFollowupAPI,
  getPatientFollowupsAPI,
  getPatientTimelineAPI,
} from '@/api/patient'
import { showError, showSuccess } from '@/utils/feedback'

defineOptions({ name: 'PatientWorkspace' })

const props = defineProps({
  patients: {
    type: Array,
    default: () => [],
  },
  patientTotal: {
    type: Number,
    default: 0,
  },
  patientsLoading: {
    type: Boolean,
    default: false,
  },
  selectedPatientId: {
    type: [Number, null],
    default: null,
  },
  patientDetail: {
    type: Object,
    default: null,
  },
  patientDetailLoading: {
    type: Boolean,
    default: false,
  },
  patientPageCount: {
    type: Number,
    default: 1,
  },
})

const query = defineModel('query', { required: true })
const analysisText = defineModel('analysisText', { default: '' })

const emit = defineEmits([
  'search',
  'select-patient',
  'open-create',
  'open-edit',
  'delete-patient',
  'analyze-patient',
  'page-change',
])

function shortText(value, fallback = '暂无内容') {
  const text = String(value || '').trim()
  return text || fallback
}

const followups = ref([])
const timeline = ref([])
const followupLoading = ref(false)
const timelineLoading = ref(false)
const completingId = ref(null)
const followupForm = ref({
  plannedDate: defaultFollowupDate(),
  followupType: 'OUTPATIENT',
  notes: '',
})
const completionForm = ref({
  mrsScore: 1,
  recurrence: 'UNKNOWN',
  adherence: 'UNKNOWN',
  notes: '',
})

function defaultFollowupDate(days = 7) {
  const date = new Date()
  date.setDate(date.getDate() + days)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatDate(value) {
  if (!value) return '未设置'
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return String(value)
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleDateString('zh-CN')
}

function followupStatusLabel(status) {
  return { PENDING: '待随访', COMPLETED: '已完成', CANCELLED: '已取消' }[status] || status || '未知'
}

function followupTypeLabel(type) {
  return { OUTPATIENT: '门诊', PHONE: '电话', WECHAT: '微信', OTHER: '其他' }[type] || '其他'
}

function timelineIcon(type) {
  return {
    patient: '👤',
    patient_update: '📝',
    stroke_assessment: '⏱️',
    ai_opinion: '🤖',
    health_data: '📈',
    followup: '📅',
  }[type] || '•'
}

async function loadPatientExtras(patientId) {
  if (!patientId) {
    followups.value = []
    timeline.value = []
    return
  }
  followupLoading.value = true
  timelineLoading.value = true
  try {
    const [followupResult, timelineResult] = await Promise.allSettled([
      getPatientFollowupsAPI(patientId),
      getPatientTimelineAPI(patientId),
    ])
    followups.value = followupResult.status === 'fulfilled' && Array.isArray(followupResult.value.data)
      ? followupResult.value.data
      : []
    timeline.value = timelineResult.status === 'fulfilled' && Array.isArray(timelineResult.value.data)
      ? timelineResult.value.data
      : []
    if (followupResult.status === 'rejected') {
      showError(followupResult.reason?.msg || '随访记录加载失败')
    }
    if (timelineResult.status === 'rejected') {
      showError(timelineResult.reason?.msg || '患者时间线加载失败')
    }
  } finally {
    followupLoading.value = false
    timelineLoading.value = false
  }
}

async function reloadPatientExtras() {
  await loadPatientExtras(props.patientDetail?.id)
}

async function submitFollowup() {
  const patientId = props.patientDetail?.id
  if (!patientId || !followupForm.value.plannedDate) return
  try {
    await createPatientFollowupAPI(patientId, {
      plannedDate: followupForm.value.plannedDate,
      followupType: followupForm.value.followupType,
      notes: followupForm.value.notes,
    })
    showSuccess('随访任务已创建')
    followupForm.value = {
      plannedDate: defaultFollowupDate(),
      followupType: 'OUTPATIENT',
      notes: '',
    }
    await reloadPatientExtras()
  } catch (error) {
    showError(error?.msg || error?.message || '随访任务创建失败')
  }
}

function beginComplete(followup) {
  completingId.value = followup.id
  completionForm.value = {
    mrsScore: followup.mrsScore ?? 1,
    recurrence: followup.recurrence || 'UNKNOWN',
    adherence: followup.adherence || 'UNKNOWN',
    notes: followup.notes || '',
  }
}

async function submitCompletion(followup) {
  const patientId = props.patientDetail?.id
  if (!patientId || !followup?.id) return
  try {
    await completePatientFollowupAPI(patientId, followup.id, {
      plannedDate: followup.plannedDate,
      mrsScore: Number(completionForm.value.mrsScore),
      recurrence: completionForm.value.recurrence,
      adherence: completionForm.value.adherence,
      notes: completionForm.value.notes,
    })
    completingId.value = null
    showSuccess('随访结局已保存')
    await reloadPatientExtras()
  } catch (error) {
    showError(error?.msg || error?.message || '随访结局保存失败')
  }
}

watch(
  () => props.patientDetail?.id,
  (patientId) => {
    loadPatientExtras(patientId)
  },
  { immediate: true },
)
function formatDateTime(value) {
  if (!value) return '暂无时间'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <section class="patient-workspace">
    <div class="patient-list-card">
      <div class="section-head wrap">
        <div>
          <h3>患者列表</h3>
          <p>支持分页筛选、新增、编辑和删除患者。</p>
        </div>
        <button type="button" class="primary-action" @click="emit('open-create')">新增患者</button>
      </div>

      <form class="toolbar" @submit.prevent="emit('search')">
        <input v-model="query.name" type="text" placeholder="按姓名筛选" />
        <input v-model="query.diseases" type="text" placeholder="按疾病史筛选" />
        <button type="submit" class="secondary-action">查询</button>
      </form>

      <div v-if="patientsLoading" class="empty-card">正在加载患者列表...</div>

      <div v-else-if="patients.length" class="patient-list">
        <article v-for="patient in patients" :key="patient.id" class="patient-item"
          :class="{ active: patient.id === selectedPatientId }" @click="emit('select-patient', patient.id)">
          <div class="patient-item-head">
            <div>
              <h4>{{ patient.name }}</h4>
              <small>患者 #{{ patient.id }}</small>
            </div>
            <span class="risk-badge">{{ patient.aiOpinion?.riskLevel || '待评估' }}</span>
          </div>

          <p>{{ shortText(patient.history) }}</p>

          <div class="patient-item-actions">
            <button type="button" class="link-btn" @click.stop="emit('open-edit', patient)">编辑</button>
            <button type="button" class="link-btn danger-text"
              @click.stop="emit('delete-patient', patient.id)">删除</button>
          </div>
        </article>
      </div>

      <div v-else class="empty-card">还没有患者数据，先新增一位患者开始管理。</div>

      <div class="pager">
        <button type="button" class="secondary-action" :disabled="query.page <= 1"
          @click="emit('page-change', -1)">上一页</button>
        <span>第 {{ query.page }} / {{ patientPageCount }} 页，共 {{ patientTotal }} 条</span>
        <button type="button" class="secondary-action" :disabled="query.page >= patientPageCount"
          @click="emit('page-change', 1)">
          下一页
        </button>
      </div>
    </div>

    <div class="patient-detail-card">
      <div class="section-head">
        <div>
          <h3>患者详情与AI意见</h3>
          <p>查看完整病史，并可追加健康数据进行风险分析。</p>
        </div>
      </div>

      <div v-if="patientDetailLoading" class="empty-card">正在加载患者详情...</div>

      <div v-else-if="patientDetail" class="detail-stack">
        <section class="detail-card">
          <div class="detail-title-row">
            <div>
              <p class="summary-label">患者信息</p>
              <h4>{{ patientDetail.name }}</h4>
            </div>
            <button type="button" class="secondary-action" @click="emit('open-edit', patientDetail)">编辑信息</button>
          </div>

          <div class="detail-grid">
            <article>
              <h5>既往病史</h5>
              <p>{{ shortText(patientDetail.history) }}</p>
            </article>
            <article>
              <h5>医生备注</h5>
              <p>{{ shortText(patientDetail.notes) }}</p>
            </article>
          </div>
        </section>

        <section class="detail-card accent">
          <div class="detail-title-row">
            <div>
              <p class="summary-label">AI分析意见</p>
              <h4>{{ patientDetail.aiOpinion?.riskLevel || '暂未生成' }}</h4>
            </div>
            <small>{{ formatDateTime(patientDetail.aiOpinion?.lastUpdatedAt) }}</small>
          </div>

          <div class="detail-grid single">
            <article>
              <h5>处理建议</h5>
              <p>{{ shortText(patientDetail.aiOpinion?.suggestion, '暂无建议') }}</p>
            </article>
            <article>
              <h5>分析详情</h5>
              <p>{{ shortText(patientDetail.aiOpinion?.analysisDetails, '暂无分析详情') }}</p>
            </article>
          </div>
        </section>

        <section class="detail-card">
          <div class="detail-title-row">
            <div>
              <p class="summary-label">手动触发AI分析</p>
              <h4>补充健康数据</h4>
            </div>
          </div>

          <textarea v-model="analysisText" class="analysis-input" rows="6"
            placeholder="例如：近三天血压持续偏高，夜间头痛加重，伴手脚麻木..."></textarea>
          <button type="button" class="primary-action" @click="emit('analyze-patient')">执行风险分析</button>
        </section>
        <section class="detail-card followup-card">
          <div class="detail-title-row">
            <div>
              <p class="summary-label">随访与结局</p>
              <h4>卒中随访管理</h4>
            </div>
            <small>{{ followups.filter((item) => item.status === 'PENDING').length }} 个待随访</small>
          </div>

          <form class="followup-create" @submit.prevent="submitFollowup">
            <input v-model="followupForm.plannedDate" type="date" required />
            <select v-model="followupForm.followupType">
              <option value="OUTPATIENT">门诊</option>
              <option value="PHONE">电话</option>
              <option value="WECHAT">微信</option>
              <option value="OTHER">其他</option>
            </select>
            <input v-model="followupForm.notes" type="text" placeholder="随访重点，如血压、用药、mRS" />
            <button type="submit" class="secondary-action">新增随访</button>
          </form>

          <div v-if="followupLoading" class="empty-inline">正在加载随访记录...</div>
          <div v-else-if="followups.length" class="followup-list">
            <article v-for="item in followups" :key="item.id" class="followup-item" :class="{ completed: item.status === 'COMPLETED' }">
              <div class="followup-item-head">
                <div>
                  <strong>{{ followupTypeLabel(item.followupType) }}随访</strong>
                  <small>计划 {{ formatDate(item.plannedDate) }}</small>
                </div>
                <span class="followup-status">{{ followupStatusLabel(item.status) }}</span>
              </div>
              <p v-if="item.status === 'COMPLETED'">
                mRS {{ item.mrsScore ?? '未填' }} · 复发 {{ item.recurrence || '未填' }} · 服药依从性 {{ item.adherence || '未填' }}
              </p>
              <p v-if="item.notes">{{ item.notes }}</p>
              <button v-if="item.status === 'PENDING'" type="button" class="link-btn" @click="beginComplete(item)">录入随访结局</button>

              <div v-if="completingId === item.id" class="completion-form">
                <label>
                  mRS
                  <select v-model="completionForm.mrsScore">
                    <option v-for="score in 7" :key="score - 1" :value="score - 1">{{ score - 1 }}</option>
                  </select>
                </label>
                <label>
                  复发
                  <select v-model="completionForm.recurrence">
                    <option value="NO">无</option>
                    <option value="YES">有</option>
                    <option value="UNKNOWN">未知</option>
                  </select>
                </label>
                <label>
                  服药依从性
                  <select v-model="completionForm.adherence">
                    <option value="GOOD">良好</option>
                    <option value="PARTIAL">部分</option>
                    <option value="POOR">差</option>
                    <option value="UNKNOWN">未知</option>
                  </select>
                </label>
                <textarea v-model="completionForm.notes" rows="2" placeholder="本次随访记录与处置"></textarea>
                <div class="completion-actions">
                  <button type="button" class="secondary-action" @click="completingId = null">取消</button>
                  <button type="button" class="primary-action" @click="submitCompletion(item)">保存结局</button>
                </div>
              </div>
            </article>
          </div>
          <div v-else class="empty-inline">暂无随访任务，可为患者创建 7/30/90 天随访。</div>
        </section>

        <section class="detail-card">
          <div class="detail-title-row">
            <div>
              <p class="summary-label">纵向健康档案</p>
              <h4>患者时间线</h4>
            </div>
            <small>评估、AI意见、健康数据与随访</small>
          </div>

          <div v-if="timelineLoading" class="empty-inline">正在加载患者时间线...</div>
          <div v-else-if="timeline.length" class="patient-timeline">
            <article v-for="(event, eventIndex) in timeline" :key="`${event.type}-${event.sourceId || eventIndex}`" class="timeline-item">
              <span class="timeline-icon">{{ timelineIcon(event.type) }}</span>
              <div class="timeline-body">
                <div class="timeline-title">
                  <strong>{{ event.title }}</strong>
                  <small>{{ formatDateTime(event.time) }}</small>
                </div>
                <p>{{ event.summary }}</p>
                <small v-if="event.status" class="timeline-status">{{ event.status }}</small>
              </div>
            </article>
          </div>
          <div v-else class="empty-inline">暂无纵向记录。完成绿道评估、AI 分析或随访后会出现在这里。</div>
        </section>
      </div>

      <div v-else class="empty-card">从左侧选择一位患者后，这里会展示完整病历和AI分析结果。</div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.patient-workspace {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

/* ─────────────────── Panels ─────────────────── */
.patient-list-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-light);
  overflow: hidden;
}

.patient-detail-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--color-bg-base);
  overflow-y: auto;
}

/* ─────────────────── Section layout ─────────────────── */
.patient-item-head,
.patient-item-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.section-head {
  flex-wrap: wrap;
  gap: 8px;
}

/* ─────────────────── Patient list ─────────────────── */
.patient-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.patient-item {
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border-item);
  cursor: pointer;
  transition: background var(--transition-fast);
  flex-shrink: 0;

  &:hover {
    background: var(--color-patient-select-hover);
  }

  &.active {
    background: var(--color-patient-select-active);
    border-left: 3px solid var(--color-active-border);
    padding-left: 11px;
  }

  h4 {
    margin: 0 0 3px;
    font-size: 13px;
    font-weight: 700;
    color: var(--color-text-strong);
  }

  p {
    margin: 0 0 5px;
    font-size: 12px;
    color: var(--color-text-medium);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    color: var(--color-text-weak);
    font-size: 11px;
  }
}

.patient-item-head {
  margin-bottom: 5px;
}

.patient-item-actions {
  justify-content: flex-start;
  gap: 14px;
}

/* ─────────────────── Risk badge ─────────────────── */
.risk-badge {
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  background: var(--color-badge-accent-bg);
  color: var(--color-orange);
  white-space: nowrap;
}

/* ─────────────────── Patient detail ─────────────────── */
.detail-stack {
  display: flex;
  flex-direction: column;
}

.detail-card h5 {
  margin: 0 0 5px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-label);
}

.detail-card p,
.detail-card small {
  color: var(--color-text-medium);
  font-size: 13px;
  margin: 0;
  line-height: 1.6;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;

  &.single {
    grid-template-columns: 1fr;
  }

  article {
    padding: 10px 12px;
    border-left: 2px solid var(--color-border);
    background: var(--color-bg-light);
  }
}

.analysis-input {
  width: 100%;
  border: 1px solid var(--color-border);
  background: var(--color-bg-input);
  border-radius: 7px;
  padding: 9px 12px;
  font: inherit;
  color: var(--color-text-strong);
  box-sizing: border-box;
  min-height: 100px;
  resize: vertical;
  margin-bottom: 10px;
}

@media (max-width: 1080px) {
  .patient-workspace {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }

  .patient-list-card {
    border-right: none;
    border-bottom: 1px solid var(--color-border);
    max-height: 340px;
    overflow: hidden;
  }
}

@media (max-width: 640px) {

  .section-head,
  .toolbar,
  .pager,
  .patient-item-head,
  .detail-title-row {
    flex-wrap: wrap;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }
}
/* ── 随访与患者时间线 ───────────────────────── */
.followup-create {
  display: grid;
  grid-template-columns: minmax(130px, 0.8fr) minmax(100px, 0.6fr) minmax(180px, 1.8fr) auto;
  gap: 8px;
  margin-bottom: 12px;
}

.followup-create input,
.followup-create select,
.completion-form select,
.completion-form textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  padding: 8px 10px;
  background: var(--color-bg-input);
  color: var(--color-text-strong);
  font: inherit;
  font-size: 12px;
}

.followup-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.followup-item {
  padding: 10px 12px;
  border: 1px solid var(--color-border-item);
  border-left: 3px solid var(--color-orange);
  border-radius: 8px;
  background: var(--color-bg-light);
}

.followup-item.completed {
  border-left-color: var(--color-active-border);
  opacity: 0.88;
}

.followup-item-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.followup-item-head strong {
  display: block;
  color: var(--color-text-strong);
  font-size: 13px;
}

.followup-item-head small {
  color: var(--color-text-weak);
  font-size: 11px;
}

.followup-status {
  flex-shrink: 0;
  border-radius: 999px;
  padding: 3px 8px;
  background: var(--color-badge-accent-bg);
  color: var(--color-orange);
  font-size: 11px;
  font-weight: 700;
}

.followup-item.completed .followup-status {
  color: var(--color-active-border);
}

.followup-item p {
  margin: 7px 0 0;
  color: var(--color-text-medium);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.followup-item .link-btn {
  margin-top: 8px;
}

.completion-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(100px, 1fr));
  gap: 8px;
  margin-top: 10px;
  padding: 10px;
  border-radius: 8px;
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-item);
}

.completion-form label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: var(--color-text-label);
  font-size: 11px;
}

.completion-form textarea,
.completion-actions {
  grid-column: 1 / -1;
}

.completion-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.patient-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-left: 4px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px dashed var(--color-border-item);
}

.timeline-item:last-child {
  border-bottom: none;
}

.timeline-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--color-bg-light);
  border: 1px solid var(--color-border-item);
  font-size: 14px;
}

.timeline-body {
  min-width: 0;
}

.timeline-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.timeline-title strong {
  color: var(--color-text-strong);
  font-size: 13px;
}

.timeline-title small {
  flex-shrink: 0;
  color: var(--color-text-weak);
  font-size: 11px;
}

.timeline-body p {
  margin: 4px 0 0;
  color: var(--color-text-medium);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.timeline-status {
  display: inline-block;
  margin-top: 5px;
  border-radius: 4px;
  padding: 2px 6px;
  background: var(--color-bg-light);
  color: var(--color-text-weak);
  font-size: 10px;
}

.empty-inline {
  padding: 12px;
  border-radius: 8px;
  background: var(--color-bg-light);
  color: var(--color-text-weak);
  font-size: 12px;
}

@media (max-width: 900px) {
  .followup-create {
    grid-template-columns: 1fr 1fr;
  }

  .followup-create input:nth-child(3) {
    grid-column: 1 / -1;
  }
}

@media (max-width: 640px) {
  .followup-create,
  .completion-form {
    grid-template-columns: 1fr;
  }

  .followup-create input:nth-child(3),
  .completion-form textarea,
  .completion-actions {
    grid-column: auto;
  }

  .timeline-title {
    flex-direction: column;
    gap: 2px;
  }
}

</style>
