<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  getCacheStatsAPI,
  getDashboardSummaryAPI,
  getKbStatusAPI,
  getOnlineUsersAPI,
  getSystemHealthAPI,
} from '@/api/dashboard'
import { getDoctorFeedbackSummaryAPI } from '@/api/feedback'
import { getStrokeAssessmentQcStatsAPI } from '@/api/strokeAssessment'
import { showError } from '@/utils/feedback'

defineOptions({ name: 'QualityWorkspace' })

const emit = defineEmits(['change-tab', 'open-review-center'])

const loading = ref(false)
const qc = ref({})
const feedback = ref({})
const dashboard = ref({})
const system = ref({ health: null, online: null, cache: null, kb: null })

const trendEntries = computed(() => Object.entries(qc.value?.trend || {}).slice(-14))
const maxTrend = computed(() => Math.max(1, ...trendEntries.value.map(([, count]) => Number(count) || 0)))
const kbData = computed(() => system.value.kb?.data || {})
const kbDocuments = computed(() => kbData.value.document_count ?? kbData.value.documents ?? '--')
const kbChunks = computed(() => kbData.value.chunk_count ?? kbData.value.chunks ?? '--')

function trendHeight(count) {
  return `${Math.max(4, Math.round((Number(count) || 0) * 100 / maxTrend.value))}%`
}

function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`
}

async function load() {
  loading.value = true
  const results = await Promise.allSettled([
    getStrokeAssessmentQcStatsAPI(),
    getDoctorFeedbackSummaryAPI(),
    getDashboardSummaryAPI(),
    getSystemHealthAPI(),
    getOnlineUsersAPI(),
    getCacheStatsAPI(),
    getKbStatusAPI(),
  ])
  const [qcRes, feedbackRes, dashboardRes, healthRes, onlineRes, cacheRes, kbRes] = results
  if (qcRes.status === 'fulfilled') qc.value = qcRes.value.data || {}
  if (feedbackRes.status === 'fulfilled') feedback.value = feedbackRes.value.data || {}
  if (dashboardRes.status === 'fulfilled') dashboard.value = dashboardRes.value.data || {}
  if (healthRes.status === 'fulfilled') system.value.health = healthRes.value.data || {}
  if (onlineRes.status === 'fulfilled') system.value.online = onlineRes.value.data || {}
  if (cacheRes.status === 'fulfilled') system.value.cache = cacheRes.value.data || {}
  if (kbRes.status === 'fulfilled') system.value.kb = kbRes.value || {}
  if (results.every((item) => item.status === 'rejected')) {
    showError('质量中心数据加载失败')
  }
  loading.value = false
}

onMounted(load)
</script>

<template>
  <section class="quality-workspace">
    <div class="quality-scroll">
      <header class="quality-header">
        <div>
          <p class="eyebrow">QUALITY &amp; SAFETY</p>
          <h2>质量与系统中心</h2>
          <p>卒中绿道过程质量、AI 回答反馈、医生复核和系统运行状态。</p>
        </div>
        <button type="button" class="secondary-action" :disabled="loading" @click="load">{{ loading ? '刷新中...' : '刷新中心' }}</button>
      </header>

      <section class="metric-grid">
        <article class="metric-card"><small>评估总数</small><strong>{{ qc.total ?? 0 }}</strong><span>绿道记录</span></article>
        <article class="metric-card"><small>DNT 中位数</small><strong>{{ qc.dntMedianMinutes ?? 0 }}<em>分钟</em></strong><span>目标持续优化</span></article>
        <article class="metric-card"><small>4.5h 窗内率</small><strong>{{ formatPercent(qc.withinWindowRate) }}</strong><span>到院至评估</span></article>
        <article class="metric-card"><small>关键字段完整率</small><strong>{{ formatPercent(qc.keyFieldCompleteRate) }}</strong><span>安全核对</span></article>
        <article class="metric-card warning"><small>风险信号命中</small><strong>{{ qc.riskHitCount ?? 0 }}</strong><span>需医生复核</span></article>
        <article class="metric-card success"><small>AI 好评率</small><strong>{{ formatPercent(feedback.positiveRate) }}</strong><span>{{ feedback.total ?? 0 }} 条反馈</span></article>
      </section>

      <div class="quality-grid">
        <section class="panel-card">
          <div class="panel-head"><div><p class="eyebrow">PROCESS TREND</p><h3>近 14 天绿道评估趋势</h3></div></div>
          <div class="trend-chart">
            <div v-for="[day, count] in trendEntries" :key="day" class="trend-column" :title="`${day}: ${count} 条`">
              <span class="trend-value">{{ count }}</span>
              <div class="trend-track"><div class="trend-fill" :style="{ height: trendHeight(count) }"></div></div>
              <small>{{ String(day).slice(5) }}</small>
            </div>
            <div v-if="!trendEntries.length" class="panel-empty">暂无趋势数据</div>
          </div>
        </section>

        <section class="panel-card">
          <div class="panel-head"><div><p class="eyebrow">FEEDBACK SIGNAL</p><h3>AI 质量反馈</h3></div><button type="button" class="link-btn" @click="emit('change-tab', 'chat')">查看问诊</button></div>
          <div class="feedback-summary">
            <div class="rate-ring"><strong>{{ formatPercent(feedback.positiveRate) }}</strong><small>好评率</small></div>
            <div class="feedback-numbers">
              <div><span>总反馈</span><strong>{{ feedback.total ?? 0 }}</strong></div>
              <div><span>有帮助</span><strong class="positive">{{ feedback.positive ?? 0 }}</strong></div>
              <div><span>需改进</span><strong class="negative">{{ feedback.negative ?? 0 }}</strong></div>
            </div>
          </div>
          <div class="review-jump">
            <div><strong>待医生复核</strong><small>报告生成前必须完成人工确认</small></div>
            <button type="button" class="mini-action" @click="emit('open-review-center')">{{ dashboard.stats?.pendingReviewCount ?? 0 }} 项待办</button>
          </div>
        </section>

        <section class="panel-card system-card">
          <div class="panel-head"><div><p class="eyebrow">SYSTEM PULSE</p><h3>运行状态</h3></div><span class="live-pill">LIVE</span></div>
          <div class="system-grid">
            <div><span>Java 后端</span><strong>{{ system.health?.status || '--' }}</strong></div>
            <div><span>在线用户</span><strong>{{ system.online?.onlineCount ?? '--' }}</strong></div>
            <div><span>知识库文档</span><strong>{{ kbDocuments }}</strong></div>
            <div><span>知识库分块</span><strong>{{ kbChunks }}</strong></div>
            <div><span>会话缓存</span><strong>{{ system.cache?.chatHistoryKeys ?? '--' }}</strong></div>
            <div><span>待持久化任务</span><strong>{{ system.cache?.persistRetryQueueSize ?? '--' }}</strong></div>
          </div>
        </section>

        <section class="panel-card action-card">
          <div class="panel-head"><div><p class="eyebrow">NEXT ACTION</p><h3>质量改进动作</h3></div></div>
          <button type="button" @click="emit('open-review-center')"><span>🛡️</span><div><strong>完成医生复核</strong><small>处理待批准的 AI 会诊结论</small></div></button>
          <button type="button" @click="emit('change-tab', 'patients')"><span>📅</span><div><strong>完成到期随访</strong><small>补录 mRS、复发与依从性</small></div></button>
          <button type="button" @click="emit('change-tab', 'greenway')"><span>⏱️</span><div><strong>补全绿道字段</strong><small>减少关键字段缺失与风险漏检</small></div></button>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.quality-workspace { height: 100%; min-height: 0; overflow: hidden; background: var(--color-bg-base); }
.quality-scroll { height: 100%; overflow-y: auto; padding: 24px; box-sizing: border-box; }
.quality-header { display: flex; justify-content: space-between; gap: 20px; align-items: flex-end; margin-bottom: 18px; }
.eyebrow { margin: 0 0 7px; color: var(--color-active-border); font-size: 10px; font-weight: 800; letter-spacing: .16em; }
.quality-header h2 { margin: 0; color: var(--color-text-strong); font-size: 24px; }
.quality-header p { margin: 7px 0 0; color: var(--color-text-medium); font-size: 12px; }
.metric-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 11px; margin-bottom: 16px; }
.metric-card { padding: 14px; border: 1px solid var(--color-border-item); border-radius: 12px; background: var(--color-bg-light); }
.metric-card small { color: var(--color-text-weak); font-size: 11px; }
.metric-card strong { display: block; margin: 8px 0 3px; color: var(--color-text-strong); font-size: 27px; }
.metric-card strong em { margin-left: 3px; font-style: normal; font-size: 12px; font-weight: 500; color: var(--color-text-weak); }
.metric-card span { color: var(--color-text-medium); font-size: 11px; }
.metric-card.warning strong { color: var(--color-orange); }
.metric-card.success strong { color: var(--color-active-border); }
.quality-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.panel-card { padding: 17px; border: 1px solid var(--color-border-item); border-radius: 14px; background: var(--color-bg-base); min-height: 210px; }
.panel-head { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; margin-bottom: 16px; }
.panel-head h3 { margin: 0; color: var(--color-text-strong); font-size: 16px; }
.link-btn { border: none; background: transparent; color: var(--color-active-border); font-size: 12px; cursor: pointer; }
.trend-chart { min-height: 135px; display: flex; align-items: flex-end; gap: 6px; padding-top: 10px; }
.trend-column { flex: 1; min-width: 0; display: flex; align-items: center; flex-direction: column; gap: 4px; height: 140px; justify-content: flex-end; }
.trend-value { color: var(--color-text-weak); font-size: 9px; }
.trend-track { width: 100%; height: 100px; display: flex; align-items: flex-end; border-radius: 4px 4px 2px 2px; background: var(--color-bg-light); overflow: hidden; }
.trend-fill { width: 100%; background: linear-gradient(to top, var(--color-primary-dark), var(--color-primary-light)); border-radius: 4px 4px 0 0; transition: height .2s ease; }
.trend-column small { color: var(--color-text-weak); font-size: 8px; white-space: nowrap; transform: scale(.9); }
.panel-empty { width: 100%; text-align: center; color: var(--color-text-weak); font-size: 12px; padding: 30px 0; }
.feedback-summary { display: flex; align-items: center; gap: 24px; }
.rate-ring { width: 112px; height: 112px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-direction: column; background: conic-gradient(var(--color-active-border) 0 78%, var(--color-bg-light) 78% 100%); position: relative; }
.rate-ring::after { content: ''; position: absolute; inset: 9px; border-radius: 50%; background: var(--color-bg-base); }
.rate-ring strong, .rate-ring small { position: relative; z-index: 1; }
.rate-ring strong { color: var(--color-text-strong); font-size: 20px; }
.rate-ring small { margin-top: 2px; color: var(--color-text-weak); font-size: 10px; }
.feedback-numbers { flex: 1; display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.feedback-numbers div { padding: 10px; border-radius: 9px; background: var(--color-bg-light); }
.feedback-numbers span { display: block; color: var(--color-text-weak); font-size: 10px; }
.feedback-numbers strong { display: block; margin-top: 5px; color: var(--color-text-strong); font-size: 20px; }
.feedback-numbers strong.positive { color: var(--color-active-border); }
.feedback-numbers strong.negative { color: var(--color-orange); }
.review-jump { display: flex; justify-content: space-between; align-items: center; margin-top: 18px; padding: 11px 12px; border: 1px dashed var(--color-border); border-radius: 9px; }
.review-jump strong { display: block; color: var(--color-text-strong); font-size: 12px; }
.review-jump small { display: block; margin-top: 3px; color: var(--color-text-weak); font-size: 10px; }
.mini-action { border: 1px solid var(--color-border); background: var(--color-bg-base); color: var(--color-active-border); border-radius: 7px; padding: 5px 9px; font-size: 11px; cursor: pointer; }
.live-pill { border-radius: 999px; padding: 4px 8px; background: var(--color-active-bg); color: var(--color-active-border); font-size: 9px; font-weight: 800; }
.system-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.system-grid div { padding: 11px; border-radius: 9px; background: var(--color-bg-light); }
.system-grid span { display: block; color: var(--color-text-weak); font-size: 10px; }
.system-grid strong { display: block; margin-top: 6px; color: var(--color-text-strong); font-size: 16px; }
.action-card { display: flex; flex-direction: column; gap: 8px; }
.action-card button { display: flex; gap: 11px; align-items: center; width: 100%; padding: 12px; border: 1px solid var(--color-border-item); border-radius: 10px; background: var(--color-bg-light); text-align: left; cursor: pointer; }
.action-card button > span { font-size: 20px; }
.action-card button strong { display: block; color: var(--color-text-strong); font-size: 12px; }
.action-card button small { display: block; margin-top: 3px; color: var(--color-text-weak); font-size: 10px; }
@media (max-width: 1050px) { .metric-grid { grid-template-columns: repeat(3, 1fr); } .quality-grid { grid-template-columns: 1fr; } }
@media (max-width: 680px) { .quality-scroll { padding: 14px; } .quality-header { flex-direction: column; align-items: flex-start; } .metric-grid { grid-template-columns: repeat(2, 1fr); } .feedback-summary { flex-direction: column; align-items: flex-start; } .system-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
