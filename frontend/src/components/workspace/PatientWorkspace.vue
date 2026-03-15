<script setup>
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
  border-right: 1px solid #d1e4df;
  background: #f8fbfa;
  overflow: hidden;
}

.patient-detail-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #fff;
  overflow-y: auto;
}

/* ─────────────────── Section heads ─────────────────── */
.section-head,
.pager,
.patient-item-head,
.patient-item-actions,
.detail-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.section-head {
  padding: 10px 14px;
  border-bottom: 1px solid #e2eeeb;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
}

.section-head {
  padding: 10px 14px;
  border-bottom: 1px solid #e2eeeb;
  flex-shrink: 0;
}

.section-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #17313a;
}

.section-head p {
  margin: 3px 0 0;
  font-size: 13px;
  color: #5e7379;
}

/* ─────────────────── Toolbar ─────────────────── */
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid #e2eeeb;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.toolbar input {
  flex: 1 1 120px;
  border: 1px solid #d1e4df;
  background: #fff;
  border-radius: 6px;
  padding: 7px 10px;
  font: inherit;
  color: #17313a;
  box-sizing: border-box;
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
  border-bottom: 1px solid #e8f0ee;
  cursor: pointer;
  transition: background 0.15s ease;
  flex-shrink: 0;
}

.patient-item:hover {
  background: rgba(17, 150, 127, 0.05);
}

.patient-item.active {
  background: rgba(17, 150, 127, 0.09);
  border-left: 3px solid #11967f;
  padding-left: 11px;
}

.patient-item h4 {
  margin: 0 0 3px;
  font-size: 13px;
  font-weight: 700;
  color: #17313a;
}

.patient-item p {
  margin: 0 0 5px;
  font-size: 12px;
  color: #5e7379;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.patient-item small {
  color: #9eb3ae;
  font-size: 11px;
}

.patient-item-head {
  margin-bottom: 5px;
}

.patient-item-actions {
  justify-content: flex-start;
  gap: 14px;
}

/* ─────────────────── Pager ─────────────────── */
.pager {
  padding: 8px 14px;
  border-top: 1px solid #e2eeeb;
  font-size: 12px;
  color: #5e7379;
  flex-shrink: 0;
}

/* ─────────────────── Buttons ─────────────────── */
.primary-action,
.secondary-action,
.link-btn {
  border: none;
  cursor: pointer;
  transition: all 0.18s ease;
}

.primary-action {
  padding: 8px 14px;
  border-radius: 7px;
  font-weight: 700;
  font-size: 13px;
  background: linear-gradient(135deg, #11967f 0%, #0f7666 100%);
  color: #fff;
}

.primary-action:hover {
  opacity: 0.88;
}

.secondary-action {
  padding: 7px 12px;
  border-radius: 7px;
  font-weight: 600;
  font-size: 13px;
  background: rgba(209, 228, 223, 0.7);
  color: #17313a;
}

.link-btn {
  background: transparent;
  padding: 0;
  color: #0f7666;
  font-size: 12px;
}

.danger-text {
  color: #dc2626;
}

/* ─────────────────── Risk badge ─────────────────── */
.risk-badge {
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
  white-space: nowrap;
}

/* ─────────────────── Patient detail ─────────────────── */
.detail-stack {
  display: flex;
  flex-direction: column;
}

.detail-card {
  padding: 14px 20px;
  border-bottom: 1px solid #e2eeeb;
}

.detail-card.accent {
  background: rgba(17, 150, 127, 0.04);
  border-left: 3px solid #11967f;
  padding-left: 17px;
}

.detail-title-row {
  margin-bottom: 10px;
}

.detail-title-row h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
}

.detail-card h5 {
  margin: 0 0 5px;
  font-size: 12px;
  font-weight: 700;
  color: #3a5a62;
}

.detail-card p,
.detail-card small {
  color: #5e7379;
  font-size: 13px;
  margin: 0;
  line-height: 1.6;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.detail-grid.single {
  grid-template-columns: 1fr;
}

.analysis-input {
  width: 100%;
  border: 1px solid #d1e4df;
  background: #fff;
  border-radius: 7px;
  padding: 9px 12px;
  font: inherit;
  color: #17313a;
  box-sizing: border-box;
  min-height: 100px;
  resize: vertical;
  margin-bottom: 10px;
}

.detail-grid article {
  padding: 10px 12px;
  border-left: 2px solid #d1e4df;
  background: #f8fbfa;
}

.summary-label {
  margin: 0 0 3px;
  font-size: 11px;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: #2c7c6e;
}

.empty-card {
  padding: 24px 16px;
  color: #9eb3ae;
  font-size: 14px;
  line-height: 1.6;
  text-align: center;
  flex-shrink: 0;
}

@media (max-width: 1080px) {
  .patient-workspace {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }

  .patient-list-card {
    border-right: none;
    border-bottom: 1px solid #d1e4df;
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
</style>