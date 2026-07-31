<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  createStrokeAssessmentAPI,
  evaluateStrokeAssessmentAPI,
  exportStrokeAssessmentFhirAPI,
  getStrokeAssessmentReviewsAPI,
  getStrokeAssessmentsAPI,
  reviewStrokeAssessmentAPI,
  updateStrokeAssessmentAPI,
} from '@/api/strokeAssessment'
import {
  buildClinicalSummary,
  buildPrintableAssessment,
  createEmptyStrokeAssessment,
  normalizeAssessmentPayload,
} from '@/utils/strokeAssessment'

defineOptions({ name: 'GreenwayWorkspace' })

const props = defineProps({
  patients: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['analyze', 'create-patient'])

const form = reactive(createEmptyStrokeAssessment())
const assessments = ref([])
const currentView = ref(null)
const reviews = ref([])
const loading = ref(false)
const evaluating = ref(false)
const saving = ref(false)
const reviewing = ref(false)
const errorMessage = ref('')
const reviewAction = ref('ACCEPT')
const reviewReason = ref('')
const dirty = ref(false)
const hydrating = ref(false)
const now = ref(Date.now())
let tickId = null

const evaluation = computed(() => currentView.value?.evaluation || null)
const selectedPatient = computed(
  () => props.patients.find((patient) => Number(patient.id) === Number(form.patientId)) || null,
)
const canReview = computed(() => Boolean(currentView.value?.id) && !dirty.value)
const canAccept = computed(
  () => canReview.value && evaluation.value?.decisionStatus === 'READY_FOR_REVIEW',
)
const onsetMinutes = computed(() => elapsedMinutes(form.lastKnownWellAt))
const doorMinutes = computed(() => elapsedMinutes(form.arrivalAt))
const thrombolysisRemaining = computed(() => remainingLabel(onsetMinutes.value, 270))
const thrombectomyRemaining = computed(() => remainingLabel(onsetMinutes.value, 1440))
const dntLabel = computed(() => {
  if (doorMinutes.value === null) return '未开始'
  return `${formatDuration(doorMinutes.value)} / 60分钟目标`
})

watch(
  form,
  () => {
    if (!hydrating.value) dirty.value = true
  },
  { deep: true },
)

onMounted(() => {
  loadAssessments()
  tickId = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onBeforeUnmount(() => {
  if (tickId) window.clearInterval(tickId)
})

async function loadAssessments() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await getStrokeAssessmentsAPI()
    assessments.value = Array.isArray(response.data) ? response.data : []
  } catch (error) {
    errorMessage.value = error?.msg || '评估记录加载失败'
  } finally {
    loading.value = false
  }
}

function startNewAssessment() {
  hydrateForm(createEmptyStrokeAssessment())
  currentView.value = null
  reviews.value = []
  reviewAction.value = 'ACCEPT'
  reviewReason.value = ''
  dirty.value = false
  errorMessage.value = ''
}

async function selectAssessment(view) {
  currentView.value = view
  hydrateForm(view.data || {})
  dirty.value = false
  errorMessage.value = ''
  await loadReviews(view.id)
}

function hydrateForm(data) {
  hydrating.value = true
  const empty = createEmptyStrokeAssessment()
  for (const key of Object.keys(empty)) {
    form[key] = toFormValue(data[key], empty[key])
  }
  requestAnimationFrame(() => {
    hydrating.value = false
  })
}

async function evaluateAssessment() {
  evaluating.value = true
  errorMessage.value = ''
  try {
    const payload = normalizeAssessmentPayload(form)
    const response = await evaluateStrokeAssessmentAPI(payload)
    currentView.value = {
      ...(currentView.value || {}),
      data: payload,
      evaluation: response.data,
      status: currentView.value?.status || 'DRAFT',
      version: currentView.value?.version || 0,
    }
    return response.data
  } catch (error) {
    errorMessage.value = error?.msg || '结构化评估失败'
    return null
  } finally {
    evaluating.value = false
  }
}

async function saveAssessment() {
  saving.value = true
  errorMessage.value = ''
  try {
    const payload = normalizeAssessmentPayload(form)
    const response = currentView.value?.id
      ? await updateStrokeAssessmentAPI(currentView.value.id, payload)
      : await createStrokeAssessmentAPI(payload)
    currentView.value = response.data
    hydrateForm(response.data.data)
    dirty.value = false
    await loadAssessments()
    await loadReviews(response.data.id)
  } catch (error) {
    errorMessage.value = error?.msg || '评估保存失败'
  } finally {
    saving.value = false
  }
}

async function submitReview() {
  if (!canReview.value) return
  if (reviewAction.value === 'ACCEPT' && !canAccept.value) {
    errorMessage.value = '存在缺失信息或高风险项，不能直接采纳'
    return
  }
  if (reviewAction.value !== 'ACCEPT' && !reviewReason.value.trim()) {
    errorMessage.value = '要求修改或驳回时必须填写原因'
    return
  }

  reviewing.value = true
  errorMessage.value = ''
  try {
    const response = await reviewStrokeAssessmentAPI(currentView.value.id, {
      action: reviewAction.value,
      reason: reviewReason.value.trim(),
    })
    currentView.value = response.data
    reviewReason.value = ''
    await Promise.all([loadAssessments(), loadReviews(response.data.id)])
  } catch (error) {
    errorMessage.value = error?.msg || '审核提交失败'
  } finally {
    reviewing.value = false
  }
}

async function loadReviews(id) {
  if (!id) {
    reviews.value = []
    return
  }
  try {
    const response = await getStrokeAssessmentReviewsAPI(id)
    reviews.value = Array.isArray(response.data) ? response.data : []
  } catch {
    reviews.value = []
  }
}

async function sendToAi() {
  const latestEvaluation =
    dirty.value || !evaluation.value ? await evaluateAssessment() : evaluation.value
  if (!latestEvaluation) return
  const payload = normalizeAssessmentPayload(form)
  emit(
    'analyze',
    buildClinicalSummary(payload, latestEvaluation, selectedPatient.value?.name || ''),
  )
}

async function downloadFhir() {
  if (!currentView.value?.id) return
  try {
    const response = await exportStrokeAssessmentFhirAPI(currentView.value.id)
    downloadBlob(
      JSON.stringify(response.data, null, 2),
      `stroke-assessment-${currentView.value.id}-v${currentView.value.version}.json`,
      'application/fhir+json;charset=utf-8',
    )
  } catch (error) {
    errorMessage.value = error?.msg || 'FHIR 导出失败'
  }
}

function printAssessment() {
  if (!currentView.value) return
  const printWindow = window.open('', '_blank')
  if (!printWindow) {
    errorMessage.value = '浏览器阻止了打印窗口'
    return
  }
  printWindow.opener = null
  printWindow.document.write(buildPrintableAssessment(currentView.value))
  printWindow.document.close()
  printWindow.focus()
  printWindow.print()
}

function setNow(field) {
  form[field] = toLocalDateTime(new Date())
}

function elapsedMinutes(value) {
  if (!value) return null
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp) || timestamp > now.value) return null
  return Math.floor((now.value - timestamp) / 60000)
}

function remainingLabel(elapsed, limit) {
  if (elapsed === null) return '待补时间'
  const remaining = limit - elapsed
  if (remaining <= 0) return `已超出 ${formatDuration(Math.abs(remaining))}`
  return `剩余 ${formatDuration(remaining)}`
}

function formatDuration(minutes) {
  const safeMinutes = Math.max(0, Number(minutes) || 0)
  const hours = Math.floor(safeMinutes / 60)
  const rest = safeMinutes % 60
  return hours ? `${hours}小时${rest}分钟` : `${rest}分钟`
}

function toLocalDateTime(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

function toFormValue(value, fallback) {
  if (value === null || value === undefined) return fallback
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) {
    return value.slice(0, 16)
  }
  return value
}

function downloadBlob(content, filename, type) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function statusLabel(status) {
  return (
    {
      DRAFT: '待审核',
      ACCEPTED: '已采纳',
      EDIT_REQUIRED: '待修改',
      REJECTED: '已驳回',
    }[status] ||
    status ||
    '待保存'
  )
}

function decisionLabel(status) {
  return (
    {
      READY_FOR_REVIEW: '可进入医生复核',
      REQUIRES_REVIEW: '信息不完整',
      BLOCKED: '已阻断自动决策',
    }[status] || '待评估'
  )
}

function reviewActionLabel(action) {
  return (
    {
      ACCEPT: '采纳',
      REQUEST_EDIT: '要求修改',
      REJECT: '驳回',
    }[action] || action
  )
}
</script>

<template>
  <section class="greenway-workspace">
    <aside class="assessment-list panel-left">
      <div class="section-head">
        <div>
          <p class="summary-label">Stroke pathway</p>
          <h3>急诊评估记录</h3>
        </div>
        <button type="button" class="primary-action" @click="startNewAssessment">新建</button>
      </div>

      <div v-if="loading" class="empty-card compact">正在加载...</div>
      <div v-else-if="!assessments.length" class="empty-card">暂无评估记录</div>
      <div v-else class="assessment-items scrollbar-thin">
        <button
          v-for="item in assessments"
          :key="item.id"
          type="button"
          class="assessment-item"
          :class="{ active: item.id === currentView?.id }"
          @click="selectAssessment(item)"
        >
          <span>
            <strong>评估 #{{ item.id }}</strong>
            <small>{{ item.data?.lastKnownWellAt || '最后正常时间未知' }}</small>
          </span>
          <span class="status-chip" :data-status="item.status">{{ statusLabel(item.status) }}</span>
        </button>
      </div>
    </aside>

    <main class="assessment-main panel-main scrollbar-thin">
      <header class="greenway-header">
        <div>
          <p class="summary-label">Acute stroke</p>
          <h2>脑卒中急诊绿色通道</h2>
        </div>
        <div class="header-actions">
          <span v-if="currentView" class="version-label"
            >v{{ currentView.version || 0 }} · {{ statusLabel(currentView.status) }}</span
          >
          <button
            type="button"
            class="secondary-action"
            :disabled="evaluating"
            @click="evaluateAssessment"
          >
            {{ evaluating ? '评估中' : '预评估' }}
          </button>
          <button type="button" class="primary-action" :disabled="saving" @click="saveAssessment">
            {{ saving ? '保存中' : '保存评估' }}
          </button>
        </div>
      </header>

      <div v-if="errorMessage" class="error-band">{{ errorMessage }}</div>

      <section class="time-strip" aria-label="急诊时间轴">
        <article>
          <span>静脉溶栓时间窗</span>
          <strong>{{ thrombolysisRemaining }}</strong>
        </article>
        <article>
          <span>取栓评估最长时间窗</span>
          <strong>{{ thrombectomyRemaining }}</strong>
        </article>
        <article :class="{ alert: doorMinutes > 60 }">
          <span>DNT 计时</span>
          <strong>{{ dntLabel }}</strong>
        </article>
      </section>

      <form class="assessment-form" @submit.prevent="saveAssessment">
        <section class="form-section">
          <div class="form-section-title">
            <span>01</span>
            <h3>患者与时间线</h3>
          </div>
          <div class="field-grid three-columns">
            <label class="field-label">
              关联患者
              <select v-model="form.patientId">
                <option value="">暂不关联</option>
                <option v-for="patient in patients" :key="patient.id" :value="patient.id">
                  {{ patient.name }} (#{{ patient.id }})
                </option>
              </select>
            </label>
            <label class="field-label">
              最后正常时间
              <span class="input-with-action">
                <input v-model="form.lastKnownWellAt" type="datetime-local" />
                <button type="button" title="设为当前时间" @click="setNow('lastKnownWellAt')">
                  现在
                </button>
              </span>
            </label>
            <label class="field-label">
              到院时间
              <span class="input-with-action">
                <input v-model="form.arrivalAt" type="datetime-local" />
                <button type="button" title="设为当前时间" @click="setNow('arrivalAt')">
                  现在
                </button>
              </span>
            </label>
          </div>
        </section>

        <section class="form-section">
          <div class="form-section-title">
            <span>02</span>
            <h3>生命体征与量表</h3>
          </div>
          <div class="field-grid four-columns">
            <label class="field-label"
              >收缩压 mmHg<input
                v-model="form.systolicBloodPressure"
                type="number"
                min="40"
                max="300"
            /></label>
            <label class="field-label"
              >舒张压 mmHg<input
                v-model="form.diastolicBloodPressure"
                type="number"
                min="20"
                max="200"
            /></label>
            <label class="field-label"
              >血糖 mmol/L<input
                v-model="form.bloodGlucoseMmolL"
                type="number"
                min="0.5"
                max="50"
                step="0.1"
            /></label>
            <label class="field-label"
              >NIHSS 总分<input v-model="form.nihssScore" type="number" min="0" max="42"
            /></label>
          </div>
        </section>

        <section class="form-section">
          <div class="form-section-title">
            <span>03</span>
            <h3>影像、检验与抗凝</h3>
          </div>
          <div class="field-grid three-columns">
            <label class="field-label"
              >头颅 CT 是否提示出血
              <select v-model="form.ctHemorrhage">
                <option value="UNKNOWN">未知</option>
                <option value="NO">否</option>
                <option value="YES">是</option>
              </select>
            </label>
            <label class="field-label"
              >CTA 是否提示大血管闭塞
              <select v-model="form.ctaLargeVesselOcclusion">
                <option value="UNKNOWN">未知</option>
                <option value="NO">否</option>
                <option value="YES">是</option>
              </select>
            </label>
            <label class="field-label"
              >是否正在使用抗凝药
              <select v-model="form.anticoagulantUse">
                <option value="UNKNOWN">未知</option>
                <option value="NO">否</option>
                <option value="YES">是</option>
              </select>
            </label>
            <label class="field-label"
              >血小板 ×10^9/L<input v-model="form.plateletCount" type="number" min="0" max="2000"
            /></label>
            <label class="field-label"
              >INR<input v-model="form.inr" type="number" min="0.1" max="20" step="0.01"
            /></label>
            <label class="field-label"
              >抗凝药末次用药时间<input
                v-model="form.anticoagulantLastDoseAt"
                type="datetime-local"
            /></label>
          </div>
          <label class="field-label notes-field"
            >补充信息<textarea v-model="form.notes" rows="3"></textarea>
          </label>
        </section>
      </form>

      <section v-if="evaluation" class="evaluation-section">
        <div class="evaluation-summary">
          <div>
            <span>信息完整度</span>
            <strong>{{ evaluation.completenessPercent }}%</strong>
          </div>
          <div class="completion-track">
            <span :style="{ width: `${evaluation.completenessPercent}%` }"></span>
          </div>
          <span class="decision-badge" :data-status="evaluation.decisionStatus">
            {{ decisionLabel(evaluation.decisionStatus) }}
          </span>
        </div>

        <div v-if="evaluation.missingFields?.length" class="result-group">
          <h3>缺失信息</h3>
          <div class="chip-row">
            <span v-for="field in evaluation.missingFields" :key="field">{{ field }}</span>
          </div>
        </div>

        <div v-if="evaluation.riskFlags?.length" class="result-group">
          <h3>风险红旗与复核动作</h3>
          <div class="risk-list">
            <article
              v-for="flag in evaluation.riskFlags"
              :key="flag.code"
              :data-severity="flag.severity"
            >
              <div>
                <strong>{{ flag.title }}</strong
                ><span>{{ flag.severity === 'CRITICAL' ? '阻断' : '提醒' }}</span>
              </div>
              <p>{{ flag.detail }}</p>
              <p class="action-line">{{ flag.requiredAction }}</p>
              <small>{{ flag.evidenceSource }}</small>
            </article>
          </div>
        </div>

        <div v-if="evaluation.changes?.length" class="result-group change-group">
          <h3>本次更新</h3>
          <ul>
            <li v-for="change in evaluation.changes" :key="change">{{ change }}</li>
          </ul>
        </div>

        <div class="decision-actions">
          <button type="button" class="primary-action" @click="sendToAi">进入多智能体分析</button>
          <button type="button" class="secondary-action" @click="printAssessment">打印报告</button>
          <button
            type="button"
            class="secondary-action"
            :disabled="!currentView?.id"
            @click="downloadFhir"
          >
            导出 FHIR JSON
          </button>
        </div>
      </section>

      <section v-if="currentView?.id" class="review-section">
        <div class="form-section-title">
          <span>04</span>
          <h3>医生审核与审计</h3>
        </div>
        <div class="review-controls">
          <div class="segmented-control">
            <button
              type="button"
              :class="{ active: reviewAction === 'ACCEPT' }"
              :disabled="!canAccept"
              @click="reviewAction = 'ACCEPT'"
            >
              采纳
            </button>
            <button
              type="button"
              :class="{ active: reviewAction === 'REQUEST_EDIT' }"
              @click="reviewAction = 'REQUEST_EDIT'"
            >
              要求修改
            </button>
            <button
              type="button"
              :class="{ active: reviewAction === 'REJECT' }"
              @click="reviewAction = 'REJECT'"
            >
              驳回
            </button>
          </div>
          <textarea
            v-if="reviewAction !== 'ACCEPT'"
            v-model="reviewReason"
            rows="2"
            placeholder="填写审核原因"
          ></textarea>
          <button
            type="button"
            class="primary-action"
            :disabled="reviewing || !canReview"
            @click="submitReview"
          >
            {{ reviewing ? '提交中' : '提交审核' }}
          </button>
        </div>

        <div v-if="reviews.length" class="audit-list">
          <article v-for="review in reviews" :key="review.id">
            <span>{{ reviewActionLabel(review.action) }} · v{{ review.assessmentVersion }}</span>
            <p>{{ review.reason || '医生确认采纳' }}</p>
            <small>{{ review.createdAt }}</small>
          </article>
        </div>
      </section>
    </main>
  </section>
</template>

<style scoped lang="scss">
.greenway-workspace {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  height: 100%;
  min-height: 0;
}
.assessment-list {
  min-width: 0;
}
.assessment-items {
  overflow-y: auto;
}
.assessment-item {
  width: 100%;
  min-height: 64px;
  padding: 10px 14px;
  border: 0;
  border-bottom: 1px solid var(--color-border-item);
  background: transparent;
  color: var(--color-text-strong);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  text-align: left;
  cursor: pointer;
}
.assessment-item:hover,
.assessment-item.active {
  background: var(--color-active-bg);
}
.assessment-item.active {
  border-left: 3px solid var(--color-primary);
  padding-left: 11px;
}
.assessment-item span:first-child {
  min-width: 0;
  display: grid;
  gap: 4px;
}
.assessment-item strong {
  font-size: 13px;
}
.assessment-item small {
  color: var(--color-text-weak);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-chip,
.decision-badge {
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 700;
  background: var(--color-badge-status-bg);
  color: var(--color-badge-status-color);
  white-space: nowrap;
}
.status-chip[data-status='ACCEPTED'] {
  background: rgba(17, 150, 127, 0.14);
  color: var(--color-primary-dark);
}
.status-chip[data-status='REJECTED'],
.decision-badge[data-status='BLOCKED'] {
  background: rgba(220, 38, 38, 0.12);
  color: var(--color-red);
}
.assessment-main {
  padding-bottom: 36px;
}
.greenway-header {
  position: sticky;
  top: 0;
  z-index: 5;
  min-height: 62px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-base);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.greenway-header h2 {
  margin: 0;
  font-size: 18px;
  letter-spacing: 0;
}
.header-actions,
.decision-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.version-label {
  color: var(--color-text-medium);
  font-size: 12px;
}
.error-band {
  padding: 9px 20px;
  background: rgba(220, 38, 38, 0.1);
  color: var(--color-red);
  border-bottom: 1px solid rgba(220, 38, 38, 0.2);
}
.time-strip {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-light);
}
.time-strip article {
  padding: 12px 20px;
  border-right: 1px solid var(--color-border);
  display: grid;
  gap: 3px;
}
.time-strip article:last-child {
  border-right: 0;
}
.time-strip span {
  font-size: 12px;
  color: var(--color-text-medium);
}
.time-strip strong {
  font-size: 16px;
  color: var(--color-text-strong);
}
.time-strip .alert strong {
  color: var(--color-red);
}
.assessment-form,
.evaluation-section,
.review-section {
  max-width: 1120px;
  width: calc(100% - 40px);
  margin: 0 auto;
}
.form-section,
.evaluation-section,
.review-section {
  padding: 20px 0;
  border-bottom: 1px solid var(--color-border-light);
}
.form-section-title {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 14px;
}
.form-section-title > span {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 700;
}
.form-section-title h3,
.result-group h3 {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-strong);
  letter-spacing: 0;
}
.field-grid {
  display: grid;
  gap: 12px;
}
.three-columns {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.four-columns {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.input-with-action {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
}
.input-with-action button {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-secondary-bg);
  color: var(--color-text-medium);
  cursor: pointer;
}
.notes-field {
  margin-top: 12px;
}
.evaluation-summary {
  display: grid;
  grid-template-columns: 150px minmax(160px, 1fr) auto;
  align-items: center;
  gap: 14px;
}
.evaluation-summary > div:first-child {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.evaluation-summary span {
  color: var(--color-text-medium);
  font-size: 13px;
}
.completion-track {
  height: 8px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--color-secondary-bg);
}
.completion-track span {
  display: block;
  height: 100%;
  background: var(--color-primary);
  transition: width 0.2s ease;
}
.decision-badge[data-status='READY_FOR_REVIEW'] {
  background: rgba(17, 150, 127, 0.14);
  color: var(--color-primary-dark);
}
.result-group {
  margin-top: 18px;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 9px;
}
.chip-row span {
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-orange);
  font-size: 12px;
}
.risk-list {
  display: grid;
  gap: 8px;
  margin-top: 9px;
}
.risk-list article {
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-orange);
  border-radius: var(--radius-sm);
  background: var(--color-bg-light);
}
.risk-list article[data-severity='CRITICAL'] {
  border-left-color: var(--color-red);
}
.risk-list article > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.risk-list article span {
  color: var(--color-red);
  font-size: 11px;
  font-weight: 700;
}
.risk-list p {
  margin: 5px 0 0;
  color: var(--color-text-medium);
  font-size: 13px;
}
.risk-list .action-line {
  color: var(--color-text-strong);
  font-weight: 600;
}
.risk-list small {
  display: block;
  margin-top: 8px;
  color: var(--color-text-weak);
}
.change-group ul {
  margin: 8px 0 0;
  padding-left: 20px;
  color: var(--color-text-medium);
}
.decision-actions {
  margin-top: 20px;
}
.review-controls {
  display: grid;
  grid-template-columns: auto minmax(220px, 1fr) auto;
  gap: 10px;
  align-items: center;
}
.segmented-control {
  display: inline-flex;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.segmented-control button {
  border: 0;
  border-right: 1px solid var(--color-border);
  padding: 8px 10px;
  background: var(--color-bg-input);
  color: var(--color-text-medium);
  cursor: pointer;
}
.segmented-control button:last-child {
  border-right: 0;
}
.segmented-control button.active {
  background: var(--color-primary);
  color: #fff;
}
.segmented-control button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.review-controls textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: var(--color-bg-input);
  color: var(--color-text-strong);
  font: inherit;
}
.audit-list {
  margin-top: 14px;
  border-top: 1px solid var(--color-border-light);
}
.audit-list article {
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border-light);
  display: grid;
  grid-template-columns: 120px 1fr auto;
  gap: 10px;
  align-items: center;
}
.audit-list span {
  font-weight: 700;
  font-size: 12px;
}
.audit-list p {
  margin: 0;
  color: var(--color-text-medium);
  font-size: 13px;
}
.audit-list small {
  color: var(--color-text-weak);
}

@media (max-width: 960px) {
  .greenway-workspace {
    grid-template-columns: 1fr;
    height: auto;
  }
  .assessment-list {
    max-height: 220px;
    border-right: 0;
    border-bottom: 1px solid var(--color-border);
  }
  .greenway-header {
    position: static;
    align-items: flex-start;
    flex-direction: column;
  }
  .time-strip,
  .three-columns,
  .four-columns {
    grid-template-columns: 1fr;
  }
  .time-strip article {
    border-right: 0;
    border-bottom: 1px solid var(--color-border);
  }
  .assessment-form,
  .evaluation-section,
  .review-section {
    width: calc(100% - 28px);
  }
  .evaluation-summary,
  .review-controls {
    grid-template-columns: 1fr;
  }
  .audit-list article {
    grid-template-columns: 1fr;
  }
}
</style>
