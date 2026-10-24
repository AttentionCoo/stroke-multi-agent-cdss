<script setup>
import { computed, ref, watch } from 'vue'
import { getReportsByTalkAPI, saveReportDraftAPI, signReportAPI } from '@/api/reports'
import { showError, showSuccess, showWarning } from '@/utils/feedback'

defineOptions({ name: 'ReportWorkbench' })

const props = defineProps({
  visible: { type: Boolean, default: false },
  talkId: { type: [String, Number], default: '' },
  messageIndex: { type: Number, default: -1 },
  initialContent: { type: String, default: '' },
  initialTitle: { type: String, default: '临床辅助分析报告' },
})
const emit = defineEmits(['close', 'saved'])

const reportTitle = ref('临床辅助分析报告')
const originalContent = ref('')
const reportContent = ref('')
const signature = ref('')
const savedReport = ref(null)
const loading = ref(false)
const saving = ref(false)
const signing = ref(false)
const showOriginal = ref(true)

const statusLabel = computed(() => savedReport.value?.status === 'SIGNED' ? '已签署' : '草稿')
const canSign = computed(() => Boolean(signature.value.trim()) && Boolean(reportContent.value.trim()) && !signing.value)

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

async function load() {
  if (!props.talkId) return
  loading.value = true
  try {
    const res = await getReportsByTalkAPI(props.talkId)
    const rows = Array.isArray(res.data) ? res.data : []
    const existing = rows.find((item) => Number(item.messageIndex) === Number(props.messageIndex))
    if (existing) {
      savedReport.value = existing
      reportTitle.value = existing.title || props.initialTitle
      originalContent.value = existing.originalContent || props.initialContent
      reportContent.value = existing.content || props.initialContent
      signature.value = existing.signature || ''
    } else {
      savedReport.value = null
      reportTitle.value = props.initialTitle
      originalContent.value = props.initialContent
      reportContent.value = props.initialContent
      signature.value = ''
    }
  } catch (error) {
    showError(error?.msg || error?.message || '报告记录加载失败')
    reportTitle.value = props.initialTitle
    originalContent.value = props.initialContent
    reportContent.value = props.initialContent
  } finally {
    loading.value = false
  }
}

async function saveDraft() {
  if (!props.talkId || props.messageIndex < 0) {
    showWarning('请先在具体 AI 回答上打开报告工作台')
    return null
  }
  if (!reportContent.value.trim()) {
    showWarning('报告内容不能为空')
    return null
  }
  saving.value = true
  try {
    const res = await saveReportDraftAPI({
      talkId: props.talkId,
      messageIndex: props.messageIndex,
      title: reportTitle.value,
      originalContent: originalContent.value,
      content: reportContent.value,
    })
    savedReport.value = res.data
    showSuccess(`报告草稿已保存，版本 v${res.data?.version || 1}`)
    emit('saved', res.data)
    return res.data
  } catch (error) {
    showError(error?.msg || error?.message || '报告保存失败')
    return null
  } finally {
    saving.value = false
  }
}

async function signReport() {
  if (!signature.value.trim()) {
    showWarning('请填写医生签名')
    return
  }
  signing.value = true
  try {
    let report = savedReport.value
    if (!report?.id) {
      report = await saveDraft()
    }
    if (!report?.id) return
    const res = await signReportAPI(report.id, signature.value)
    savedReport.value = res.data
    showSuccess('报告已签署，修改前的版本仍保留在审计记录中')
    emit('saved', res.data)
  } catch (error) {
    showError(error?.msg || error?.message || '报告签署失败')
  } finally {
    signing.value = false
  }
}

function download(filename, content, mime) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function safeFileName() {
  return `${reportTitle.value || '临床报告'}-${new Date().toISOString().slice(0, 10)}`
}

function exportMarkdown() {
  download(`${safeFileName()}.md`, reportContent.value, 'text/markdown;charset=utf-8')
}

function exportWord() {
  const html = `<html><head><meta charset="utf-8"><title>${escapeHtml(reportTitle.value)}</title></head><body><h1>${escapeHtml(reportTitle.value)}</h1><pre style="white-space:pre-wrap;font-family:inherit">${escapeHtml(reportContent.value)}</pre>${signature.value ? `<p>审核医师：${escapeHtml(signature.value)}</p>` : ''}</body></html>`
  download(`${safeFileName()}.doc`, html, 'application/msword;charset=utf-8')
}

function exportJson() {
  download(`${safeFileName()}.json`, JSON.stringify({
    title: reportTitle.value,
    content: reportContent.value,
    originalContent: originalContent.value,
    signature: signature.value,
    status: savedReport.value?.status || 'DRAFT',
    version: savedReport.value?.version || null,
  }, null, 2), 'application/json;charset=utf-8')
}

function printReport() {
  const printWindow = window.open('', '_blank')
  if (!printWindow) {
    showWarning('浏览器阻止了打印窗口，请允许弹窗')
    return
  }
  printWindow.document.write(`<html><head><meta charset="utf-8"><title>${escapeHtml(reportTitle.value)}</title><style>body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.8;padding:42px;color:#17313a}h1{font-size:22px;border-bottom:1px solid #d1e4df;padding-bottom:12px}pre{white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:14px}.sign{margin-top:48px;text-align:right}.meta{color:#667;font-size:12px}</style></head><body><h1>${escapeHtml(reportTitle.value)}</h1><p class="meta">生成时间：${new Date().toLocaleString('zh-CN')} · 状态：${statusLabel.value}</p><pre>${escapeHtml(reportContent.value)}</pre>${signature.value ? `<p class="sign">审核医师：${escapeHtml(signature.value)}</p>` : ''}<p class="meta">本报告为 AI 辅助分析，需结合临床资料并由医生最终确认。</p></body></html>`)
  printWindow.document.close()
  printWindow.focus()
  printWindow.print()
}

watch(() => props.visible, (visible) => {
  if (visible) load()
}, { immediate: true })
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="report-backdrop" @click.self="emit('close')">
      <section class="report-workbench">
        <header class="report-header">
          <div>
            <p class="eyebrow">AI REPORT WORKBENCH</p>
            <h3>报告编辑与签署</h3>
          </div>
          <div class="report-status">
            <span :class="{ signed: savedReport?.status === 'SIGNED' }">{{ statusLabel }}</span>
            <small v-if="savedReport?.version">v{{ savedReport.version }}</small>
            <button type="button" class="close-btn" @click="emit('close')">×</button>
          </div>
        </header>

        <div v-if="loading" class="loading">正在加载报告版本...</div>
        <div v-else class="report-body">
          <div class="editor-column">
            <label>报告标题<input v-model="reportTitle" type="text" maxlength="255" /></label>
            <label class="editor-label">
              医生编辑稿
              <textarea v-model="reportContent" rows="18" placeholder="编辑 AI 报告内容..."></textarea>
            </label>
            <div class="signature-row">
              <label>医生签名<input v-model="signature" type="text" maxlength="100" placeholder="输入姓名作为电子签名" /></label>
              <button type="button" class="sign-btn" :disabled="!canSign" @click="signReport">{{ signing ? '签署中...' : '签署并锁定' }}</button>
            </div>
          </div>

          <aside class="original-column">
            <div class="original-head">
              <strong>AI 原始稿</strong>
              <button type="button" class="text-btn" @click="showOriginal = !showOriginal">{{ showOriginal ? '收起' : '展开' }}</button>
            </div>
            <pre v-if="showOriginal">{{ originalContent || '暂无原始内容' }}</pre>
            <div class="diff-hint">编辑稿与原始稿同时保留；签署后修改会生成新版本。</div>
          </aside>
        </div>

        <footer class="report-footer">
          <div class="export-actions">
            <button type="button" class="secondary-action" @click="exportMarkdown">导出 Markdown</button>
            <button type="button" class="secondary-action" @click="exportWord">导出 Word</button>
            <button type="button" class="secondary-action" @click="exportJson">导出 JSON</button>
            <button type="button" class="secondary-action" @click="printReport">打印 / PDF</button>
          </div>
          <div class="save-actions">
            <button type="button" class="secondary-action" :disabled="saving" @click="saveDraft">{{ saving ? '保存中...' : '保存草稿' }}</button>
            <button type="button" class="primary-action" @click="emit('close')">关闭</button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.report-backdrop { position: fixed; inset: 0; z-index: 160; display: flex; align-items: center; justify-content: center; padding: 18px; background: rgba(15, 23, 42, .52); backdrop-filter: blur(5px); }
.report-workbench { width: min(1180px, 100%); height: min(88vh, 900px); display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--color-dialog-border); border-radius: 16px; background: var(--color-dialog-bg); box-shadow: 0 32px 100px rgba(15, 23, 42, .34); }
.report-header { display: flex; justify-content: space-between; align-items: flex-start; padding: 17px 21px; border-bottom: 1px solid var(--color-border-item); }
.eyebrow { margin: 0 0 5px; color: var(--color-active-border); font-size: 9px; font-weight: 800; letter-spacing: .16em; }
.report-header h3 { margin: 0; color: var(--color-text-strong); font-size: 20px; }
.report-status { display: flex; gap: 8px; align-items: center; }
.report-status span { border-radius: 999px; padding: 4px 9px; background: var(--color-badge-accent-bg); color: var(--color-orange); font-size: 10px; font-weight: 800; }
.report-status span.signed { background: var(--color-active-bg); color: var(--color-active-border); }
.report-status small { color: var(--color-text-weak); font-size: 10px; }
.close-btn { border: none; background: transparent; color: var(--color-text-medium); font-size: 26px; cursor: pointer; }
.report-body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr); gap: 16px; padding: 16px 20px; overflow: hidden; }
.editor-column { display: flex; flex-direction: column; min-height: 0; }
.editor-column label, .signature-row label { display: flex; flex-direction: column; gap: 6px; color: var(--color-text-label); font-size: 11px; font-weight: 700; }
.editor-column input, .editor-column textarea, .signature-row input { box-sizing: border-box; border: 1px solid var(--color-border); border-radius: 8px; padding: 9px 11px; background: var(--color-bg-input); color: var(--color-text-strong); font: inherit; font-size: 12px; }
.editor-label { flex: 1; min-height: 0; margin-top: 10px; }
.editor-column textarea { flex: 1; min-height: 260px; resize: none; line-height: 1.65; }
.signature-row { display: flex; align-items: flex-end; gap: 10px; margin-top: 10px; }
.signature-row label { flex: 1; }
.sign-btn { border: 1px solid var(--color-active-border); background: var(--color-active-border); color: #fff; border-radius: 8px; padding: 9px 12px; font-size: 11px; font-weight: 800; cursor: pointer; white-space: nowrap; }
.sign-btn:disabled { opacity: .45; cursor: not-allowed; }
.original-column { display: flex; flex-direction: column; min-height: 0; padding: 12px; border: 1px solid var(--color-border-item); border-radius: 10px; background: var(--color-bg-light); }
.original-head { display: flex; justify-content: space-between; align-items: center; }
.original-head strong { color: var(--color-text-strong); font-size: 12px; }
.text-btn { border: none; background: transparent; color: var(--color-active-border); font-size: 10px; cursor: pointer; }
.original-column pre { flex: 1; overflow: auto; margin: 10px 0; padding: 0; white-space: pre-wrap; word-break: break-word; color: var(--color-text-medium); font-family: inherit; font-size: 11px; line-height: 1.7; }
.diff-hint { padding-top: 10px; border-top: 1px dashed var(--color-border); color: var(--color-text-weak); font-size: 10px; line-height: 1.5; }
.loading { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--color-text-weak); font-size: 12px; }
.report-footer { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 13px 20px; border-top: 1px solid var(--color-border-item); }
.export-actions, .save-actions { display: flex; flex-wrap: wrap; gap: 7px; }
@media (max-width: 900px) { .report-body { grid-template-columns: 1fr; overflow-y: auto; } .original-column { max-height: 220px; } .report-footer { flex-direction: column; align-items: stretch; } }
</style>
