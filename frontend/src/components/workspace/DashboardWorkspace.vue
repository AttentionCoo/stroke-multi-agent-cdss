<script setup>
import { computed, onMounted, ref } from 'vue'
import { useUserStore } from '@/stores/user'
import { getDashboardSummaryAPI } from '@/api/dashboard'
import { showError } from '@/utils/feedback'

defineOptions({ name: 'DashboardWorkspace' })

const emit = defineEmits(['change-tab', 'open-patient', 'open-talk', 'open-review-center'])
const userStore = useUserStore()
const summary = ref(null)
const loading = ref(false)

const stats = computed(() => summary.value?.stats || {})
const pendingReviews = computed(() => summary.value?.pendingReviews || [])
const dueFollowups = computed(() => summary.value?.dueFollowups || [])
const recentAssessments = computed(() => summary.value?.recentAssessments || [])
const recentPatients = computed(() => summary.value?.recentPatients || [])

function formatDateTime(value) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusLabel(status) {
  return {
    DRAFT: '待审核',
    ACCEPTED: '已采纳',
    REQUEST_EDIT: '需修改',
    REJECTED: '已驳回',
  }[status] || status || '未知'
}

async function load() {
  loading.value = true
  try {
    const res = await getDashboardSummaryAPI()
    summary.value = res.data || null
  } catch (error) {
    showError(error?.msg || error?.message || '工作台数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
defineExpose({ load })
</script>

<template>
  <section class="dashboard-workspace">
    <div class="dashboard-scroll">
      <header class="welcome-card">
        <div>
          <p class="eyebrow">CLINICAL COMMAND CENTER</p>
          <h2>您好，{{ userStore.name || '医生' }}</h2>
          <p class="welcome-desc">这里是今日卒中诊疗、会诊复核与患者随访的统一工作台。</p>
        </div>
        <div class="quick-actions">
          <button type="button" class="primary-action" @click="emit('change-tab', 'chat')">开始智能问诊</button>
          <button type="button" class="secondary-action" @click="emit('change-tab', 'greenway')">新建绿道评估</button>
          <button type="button" class="secondary-action" @click="emit('change-tab', 'patients')">患者管理</button>
          <button type="button" class="ghost-btn" :disabled="loading" @click="load">{{ loading ? '刷新中...' : '刷新数据' }}</button>
        </div>
      </header>

      <div class="stats-grid">
        <article class="stat-card">
          <span class="stat-icon">👤</span>
          <div><strong>{{ stats.patientCount ?? 0 }}</strong><small>在管患者</small></div>
        </article>
        <article class="stat-card warning" @click="emit('open-review-center')">
          <span class="stat-icon">🛡️</span>
          <div><strong>{{ stats.pendingReviewCount ?? 0 }}</strong><small>待医生复核</small></div>
        </article>
        <article class="stat-card danger">
          <span class="stat-icon">📅</span>
          <div><strong>{{ stats.dueFollowupCount ?? 0 }}</strong><small>到期随访</small></div>
        </article>
        <article class="stat-card" @click="emit('change-tab', 'greenway')">
          <span class="stat-icon">⏱️</span>
          <div><strong>{{ stats.assessmentCount ?? 0 }}</strong><small>绿道评估</small></div>
        </article>
        <article class="stat-card">
          <span class="stat-icon">✍️</span>
          <div><strong>{{ stats.signedReportCount ?? 0 }}</strong><small>已签署报告</small></div>
        </article>
        <article class="stat-card success">
          <span class="stat-icon">⭐</span>
          <div><strong>{{ stats.feedbackPositiveRate ?? 0 }}%</strong><small>AI 回答好评率</small></div>
        </article>
      </div>

      <div v-if="loading && !summary" class="dashboard-empty">正在加载工作台数据...</div>

      <div v-else class="dashboard-grid">
        <section class="panel-card review-panel">
          <div class="panel-head">
            <div><p class="panel-kicker">REVIEW QUEUE</p><h3>待复核会诊</h3></div>
            <button type="button" class="link-btn" @click="emit('open-review-center')">全部复核</button>
          </div>
          <div v-if="pendingReviews.length" class="compact-list">
            <article v-for="task in pendingReviews" :key="task.taskId" class="compact-item">
              <div>
                <strong>复核任务 #{{ task.taskId }}</strong>
                <small>{{ task.payload?.title || '会诊结论待医生批准或驳回' }}</small>
              </div>
              <div class="item-right">
                <span class="time">{{ formatDateTime(task.updatedAt) }}</span>
                <button type="button" class="mini-action" @click="emit('open-review-center')">去复核</button>
              </div>
            </article>
          </div>
          <div v-else class="panel-empty">暂无待复核会诊。AI 报告仍需医生最终确认。</div>
        </section>

        <section class="panel-card followup-panel">
          <div class="panel-head">
            <div><p class="panel-kicker">FOLLOW-UP</p><h3>到期随访</h3></div>
            <button type="button" class="link-btn" @click="emit('change-tab', 'patients')">患者列表</button>
          </div>
          <div v-if="dueFollowups.length" class="compact-list">
            <article v-for="item in dueFollowups" :key="item.id" class="compact-item">
              <div>
                <strong>{{ item.patientName }}</strong>
                <small>{{ item.followupType || '门诊' }}随访 · 计划 {{ item.plannedDate }}</small>
              </div>
              <button type="button" class="mini-action" @click="emit('open-patient', item.patientId)">录入结局</button>
            </article>
          </div>
          <div v-else class="panel-empty">暂无到期随访。</div>
        </section>

        <section class="panel-card assessment-panel">
          <div class="panel-head">
            <div><p class="panel-kicker">STROKE GREENWAY</p><h3>近期绿道评估</h3></div>
            <button type="button" class="link-btn" @click="emit('change-tab', 'greenway')">进入绿道</button>
          </div>
          <div v-if="recentAssessments.length" class="compact-list">
            <article v-for="item in recentAssessments" :key="item.id" class="compact-item">
              <div>
                <strong>{{ item.patientName }}</strong>
                <small>NIHSS {{ item.nihssScore ?? '未填' }} · {{ statusLabel(item.status) }}</small>
              </div>
              <span class="time">{{ formatDateTime(item.updatedAt) }}</span>
            </article>
          </div>
          <div v-else class="panel-empty">暂无绿道评估记录。</div>
        </section>

        <section class="panel-card recent-patient-panel">
          <div class="panel-head">
            <div><p class="panel-kicker">PATIENT TIMELINE</p><h3>最近患者</h3></div>
            <button type="button" class="link-btn" @click="emit('change-tab', 'patients')">全部患者</button>
          </div>
          <div v-if="recentPatients.length" class="patient-grid">
            <button v-for="patient in recentPatients" :key="patient.id" type="button" class="patient-chip"
              @click="emit('open-patient', patient.id)">
              <span class="avatar-dot">{{ (patient.name || '患').slice(0, 1) }}</span>
              <span><strong>{{ patient.name }}</strong><small>{{ patient.history || '暂无病史摘要' }}</small></span>
            </button>
          </div>
          <div v-else class="panel-empty">还没有患者档案。</div>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.dashboard-workspace { height: 100%; min-height: 0; overflow: hidden; background: var(--color-bg-base); }
.dashboard-scroll { height: 100%; overflow-y: auto; padding: 24px; box-sizing: border-box; }
.welcome-card { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; padding: 24px; border-radius: 18px; background: linear-gradient(135deg, rgba(17,150,127,.12), rgba(59,130,246,.07)); border: 1px solid var(--color-border); }
.eyebrow, .panel-kicker { margin: 0 0 7px; color: var(--color-active-border); font-size: 10px; font-weight: 800; letter-spacing: .16em; }
.welcome-card h2 { margin: 0; font-size: 26px; color: var(--color-text-strong); }
.welcome-desc { margin: 8px 0 0; color: var(--color-text-medium); font-size: 13px; }
.quick-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.ghost-btn { border: 1px solid var(--color-border); background: var(--color-bg-base); color: var(--color-text-medium); border-radius: 8px; padding: 8px 12px; cursor: pointer; font: inherit; font-size: 12px; }
.stats-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }
.stat-card { display: flex; gap: 10px; align-items: center; padding: 15px 16px; border: 1px solid var(--color-border-item); border-radius: 12px; background: var(--color-bg-light); cursor: default; }
.stat-card.warning, .stat-card.danger, .stat-card.success { cursor: pointer; }
.stat-icon { font-size: 22px; }
.stat-card strong { display: block; font-size: 25px; color: var(--color-text-strong); line-height: 1; }
.stat-card small { display: block; margin-top: 6px; color: var(--color-text-weak); font-size: 11px; }
.dashboard-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.panel-card { padding: 16px; border: 1px solid var(--color-border-item); border-radius: 14px; background: var(--color-bg-base); min-height: 180px; }
.recent-patient-panel { grid-column: 1 / -1; }
.panel-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 12px; }
.panel-head h3 { margin: 0; font-size: 16px; color: var(--color-text-strong); }
.compact-list { display: flex; flex-direction: column; }
.compact-item { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 11px 0; border-bottom: 1px dashed var(--color-border-item); }
.compact-item:last-child { border-bottom: none; }
.compact-item strong { display: block; color: var(--color-text-strong); font-size: 13px; }
.compact-item small { display: block; margin-top: 4px; color: var(--color-text-medium); font-size: 12px; }
.item-right { display: flex; flex-direction: column; align-items: flex-end; gap: 5px; }
.time { color: var(--color-text-weak); font-size: 11px; white-space: nowrap; }
.mini-action { border: 1px solid var(--color-border); background: var(--color-bg-light); color: var(--color-active-border); border-radius: 7px; padding: 4px 9px; font-size: 11px; cursor: pointer; }
.panel-empty, .dashboard-empty { padding: 28px 14px; border-radius: 10px; background: var(--color-bg-light); color: var(--color-text-weak); font-size: 12px; text-align: center; }
.patient-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.patient-chip { display: flex; gap: 9px; align-items: center; width: 100%; padding: 10px; border: 1px solid var(--color-border-item); border-radius: 10px; background: var(--color-bg-light); text-align: left; cursor: pointer; }
.avatar-dot { flex: 0 0 28px; height: 28px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; background: var(--color-active-bg); color: var(--color-active-border); font-size: 12px; font-weight: 800; }
.patient-chip strong { display: block; color: var(--color-text-strong); font-size: 12px; }
.patient-chip small { display: block; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text-weak); font-size: 11px; max-width: 160px; }
@media (max-width: 1100px) { .stats-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } .welcome-card { flex-direction: column; align-items: flex-start; } .quick-actions { justify-content: flex-start; } }
@media (max-width: 720px) { .dashboard-scroll { padding: 14px; } .dashboard-grid { grid-template-columns: 1fr; } .recent-patient-panel { grid-column: auto; } .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .patient-grid { grid-template-columns: 1fr; } }
</style>
