const FIELD_LABELS = {
  patientId: '患者ID',
  lastKnownWellAt: '最后正常时间',
  arrivalAt: '到院时间',
  systolicBloodPressure: '收缩压',
  diastolicBloodPressure: '舒张压',
  bloodGlucoseMmolL: '血糖',
  nihssScore: 'NIHSS评分',
  plateletCount: '血小板计数',
  inr: 'INR',
  anticoagulantUse: '抗凝药使用',
  anticoagulantLastDoseAt: '抗凝药末次用药时间',
  ctHemorrhage: '头颅CT提示出血',
  ctaLargeVesselOcclusion: 'CTA提示大血管闭塞',
  notes: '补充信息',
}

const NUMBER_FIELDS = [
  'patientId',
  'systolicBloodPressure',
  'diastolicBloodPressure',
  'bloodGlucoseMmolL',
  'nihssScore',
  'plateletCount',
  'inr',
]

const DATE_FIELDS = ['lastKnownWellAt', 'arrivalAt', 'anticoagulantLastDoseAt']
const STATE_FIELDS = ['anticoagulantUse', 'ctHemorrhage', 'ctaLargeVesselOcclusion']

export function createEmptyStrokeAssessment() {
  return {
    patientId: '',
    lastKnownWellAt: '',
    arrivalAt: '',
    systolicBloodPressure: '',
    diastolicBloodPressure: '',
    bloodGlucoseMmolL: '',
    nihssScore: '',
    plateletCount: '',
    inr: '',
    anticoagulantUse: 'UNKNOWN',
    anticoagulantLastDoseAt: '',
    ctHemorrhage: 'UNKNOWN',
    ctaLargeVesselOcclusion: 'UNKNOWN',
    notes: '',
  }
}

export function normalizeAssessmentPayload(form = {}) {
  const normalized = createEmptyStrokeAssessment()

  for (const field of NUMBER_FIELDS) {
    normalized[field] = toNumberOrNull(form[field])
  }
  for (const field of DATE_FIELDS) {
    normalized[field] = blankToNull(form[field])
  }
  for (const field of STATE_FIELDS) {
    normalized[field] = form[field] || 'UNKNOWN'
  }
  normalized.notes = String(form.notes || '').trim()
  return normalized
}

export function buildClinicalSummary(data, evaluation = {}, patientName = '') {
  const value = (field, suffix = '') => {
    const current = data?.[field]
    if (current === null || current === undefined || current === '' || current === 'UNKNOWN')
      return '未知'
    if (current === 'YES') return '是'
    if (current === 'NO') return '否'
    return `${current}${suffix}`
  }

  const missing = evaluation.missingFields?.length ? evaluation.missingFields.join('、') : '无'
  const flags = evaluation.riskFlags?.length
    ? evaluation.riskFlags.map((flag) => flag.title).join('；')
    : '未触发确定性风险规则'

  return [
    '【脑卒中急诊绿色通道结构化评估】',
    `患者：${patientName || (data.patientId ? `#${data.patientId}` : '未关联患者')}`,
    `最后正常时间：${value('lastKnownWellAt')}`,
    `到院时间：${value('arrivalAt')}`,
    `血压：${value('systolicBloodPressure')}/${value('diastolicBloodPressure')} mmHg`,
    `血糖：${value('bloodGlucoseMmolL', ' mmol/L')}`,
    `NIHSS评分：${value('nihssScore')}`,
    `血小板计数：${value('plateletCount', '×10^9/L')}`,
    `INR：${value('inr')}`,
    `正在使用抗凝药：${value('anticoagulantUse')}`,
    `抗凝药末次用药时间：${value('anticoagulantLastDoseAt')}`,
    `头颅CT提示出血：${value('ctHemorrhage')}`,
    `CTA提示大血管闭塞：${value('ctaLargeVesselOcclusion')}`,
    `补充信息：${value('notes')}`,
    `缺失信息：${missing}`,
    `确定性规则提示：${flags}`,
    '',
    '请基于现有多智能体流程进行分析。不得假设未知字段，并在结论中明确缺失信息的影响。',
  ].join('\n')
}

export function buildEvidenceCards(markdown = '') {
  const cards = []
  for (const rawLine of String(markdown).split(/\r?\n/)) {
    const sources = [...rawLine.matchAll(/《([^》]+)》/g)].map((match) => match[1].trim())
    if (!sources.length) continue
    const statement = rawLine
      .replace(/《[^》]+》/g, '')
      .replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s*)/, '')
      .trim()
    if (!statement) continue
    cards.push({
      statement,
      sources: [...new Set(sources)],
    })
  }
  return cards
}

export function buildPrintableAssessment(view = {}) {
  const data = view.data || {}
  const evaluation = view.evaluation || {}
  const rows = Object.entries(FIELD_LABELS)
    .map(
      ([field, label]) =>
        `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(displayValue(data[field]))}</td></tr>`,
    )
    .join('')
  const missing = (evaluation.missingFields || []).map(escapeHtml).join('、') || '无'
  const risks =
    (evaluation.riskFlags || [])
      .map(
        (flag) =>
          `<li><strong>${escapeHtml(flag.title)}</strong>：` +
          `${escapeHtml(flag.requiredAction || flag.detail || '')}</li>`,
      )
      .join('') || '<li>未触发确定性风险规则</li>'

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>脑卒中急诊评估 #${escapeHtml(view.id ?? '-')}</title>
  <style>
    body{
      font-family:Arial,"Microsoft YaHei",sans-serif;
      color:#172b33;
      margin:32px;
      line-height:1.55
    }
    h1{font-size:22px;margin:0 0 6px} .meta{color:#5e7379;margin-bottom:20px}
    table{width:100%;border-collapse:collapse;margin:16px 0}
    th,td{border:1px solid #d1e4df;padding:8px;text-align:left}
    th{width:220px;background:#f4f8f7}
    h2{font-size:16px;margin-top:24px}
    .notice{border-left:4px solid #b45309;padding:10px 14px;background:#fff7ed}
    @media print{body{margin:12mm}.no-print{display:none}}
  </style>
</head>
<body>
  <h1>脑卒中急诊结构化评估</h1>
  <div class="meta">
    评估 #${escapeHtml(view.id ?? '-')} · 版本 ${escapeHtml(view.version ?? '-')} ·
    审核状态 ${escapeHtml(view.status || 'DRAFT')}
  </div>
  <div class="notice">本报告为临床辅助决策原型输出，必须由具备资质的临床医生复核。</div>
  <h2>结构化信息</h2><table>${rows}</table>
  <h2>完整度</h2><p>${escapeHtml(evaluation.completenessPercent ?? 0)}%；缺失信息：${missing}</p>
  <h2>风险与复核动作</h2><ul>${risks}</ul>
</body>
</html>`
}

function toNumberOrNull(value) {
  if (value === '' || value === null || value === undefined) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function blankToNull(value) {
  const text = String(value || '').trim()
  return text || null
}

function displayValue(value) {
  if (value === null || value === undefined || value === '' || value === 'UNKNOWN') return '未知'
  if (value === 'YES') return '是'
  if (value === 'NO') return '否'
  return String(value)
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}
