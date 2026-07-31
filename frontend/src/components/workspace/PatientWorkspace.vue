<script setup>
defineOptions({ name: 'PatientWorkspace' })

defineProps({
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
</style>
