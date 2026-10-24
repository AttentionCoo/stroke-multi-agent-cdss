<script setup>
import { computed, ref } from 'vue'
import { copyText } from '@/utils/clipboard'
import { showSuccess } from '@/utils/feedback'

defineOptions({ name: 'ClinicalCalculatorDrawer' })

defineProps({ visible: { type: Boolean, default: false } })
const emit = defineEmits(['close'])

const activeTool = ref('rtpa')
const weight = ref(70)
const onset = ref(localDateTimeValue(new Date(Date.now() - 2 * 60 * 60 * 1000)))
const gcsEye = ref(4)
const gcsVerbal = ref(5)
const gcsMotor = ref(6)
const mrs = ref(0)
const cha2 = ref({ chf: false, hypertension: false, age75: false, diabetes: false, stroke: false, vascular: false, age65: false, female: false })
const hasBled = ref({ hypertension: false, renal: false, liver: false, stroke: false, bleeding: false, labileInr: false, elderly: false, drugs: false, alcohol: false })

const tools = [
  { key: 'rtpa', label: 'rt-PA 剂量' },
  { key: 'window', label: '溶栓时间窗' },
  { key: 'gcs', label: 'GCS' },
  { key: 'mrs', label: 'mRS' },
  { key: 'cha2', label: 'CHA₂DS₂-VASc' },
  { key: 'hasbled', label: 'HAS-BLED' },
]

const mrsDescriptions = [
  '0 分：完全无症状',
  '1 分：有症状但无明显残疾，可完成日常生活',
  '2 分：轻度残疾，不能完成所有既往活动，但可自理',
  '3 分：中度残疾，需要部分帮助，但可独立行走',
  '4 分：中重度残疾，不能独立行走，日常生活需帮助',
  '5 分：重度残疾，卧床、失禁，需持续护理',
  '6 分：死亡',
]

function localDateTimeValue(date) {
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const rtpaDose = computed(() => {
  const w = Number(weight.value)
  if (!Number.isFinite(w) || w <= 0) return { total: 0, bolus: 0, infusion: 0 }
  const total = Math.min(90, w * 0.9)
  return { total: round(total), bolus: round(total * 0.1), infusion: round(total * 0.9) }
})

function round(value) {
  return Math.round(value * 10) / 10
}

const windowInfo = computed(() => {
  if (!onset.value) return { minutes: null, label: '请选择最后正常时间', tone: 'muted' }
  const diff = Date.now() - new Date(onset.value).getTime()
  if (!Number.isFinite(diff) || diff < 0) return { minutes: null, label: '时间无效或位于未来', tone: 'danger' }
  const minutes = Math.round(diff / 60000)
  if (minutes <= 270) return { minutes, label: '处于 4.5 小时静脉溶栓参考窗口内', tone: 'success' }
  if (minutes <= 1440) return { minutes, label: '超过 4.5 小时，仍在 24 小时取栓评估参考窗口内', tone: 'warning' }
  return { minutes, label: '超过 24 小时，按延迟就诊路径评估', tone: 'muted' }
})

const gcsTotal = computed(() => Number(gcsEye.value) + Number(gcsVerbal.value) + Number(gcsMotor.value))
const gcsLabel = computed(() => {
  if (gcsTotal.value >= 13) return '轻度意识障碍 / 基本清醒'
  if (gcsTotal.value >= 9) return '中度意识障碍'
  return '重度意识障碍，需紧急处理'
})

const cha2Score = computed(() => {
  const v = cha2.value
  return (v.chf ? 1 : 0) + (v.hypertension ? 1 : 0) + (v.age75 ? 2 : 0)
    + (v.diabetes ? 1 : 0) + (v.stroke ? 2 : 0) + (v.vascular ? 1 : 0)
    + (v.age65 ? 1 : 0) + (v.female ? 1 : 0)
})

const hasBledScore = computed(() => {
  const v = hasBled.value
  return (v.hypertension ? 1 : 0) + (v.renal ? 1 : 0) + (v.liver ? 1 : 0)
    + (v.stroke ? 1 : 0) + (v.bleeding ? 1 : 0) + (v.labileInr ? 1 : 0)
    + (v.elderly ? 1 : 0) + (v.drugs ? 1 : 0) + (v.alcohol ? 1 : 0)
})

const resultText = computed(() => {
  if (activeTool.value === 'rtpa') {
    return `rt-PA 参考剂量（0.9 mg/kg，最大 90 mg）\n体重：${weight.value} kg\n总剂量：${rtpaDose.value.total} mg\n10% 首剂推注：${rtpaDose.value.bolus} mg\n90% 静滴：${rtpaDose.value.infusion} mg\n\n需先排除出血、血压、血小板、INR 等禁忌并完成知情同意。`
  }
  if (activeTool.value === 'window') {
    return `溶栓时间窗判断\n最后正常时间：${onset.value || '未填写'}\n距现在：${windowInfo.value.minutes ?? '--'} 分钟\n结论：${windowInfo.value.label}\n\n时间窗仅为参考，是否治疗需结合影像、实验室和医生判断。`
  }
  if (activeTool.value === 'gcs') {
    return `GCS 评分\nE${gcsEye.value} + V${gcsVerbal.value} + M${gcsMotor.value} = ${gcsTotal.value} 分\n${gcsLabel.value}`
  }
  if (activeTool.value === 'mrs') {
    return `mRS 功能结局\n${mrsDescriptions[Number(mrs.value)]}`
  }
  if (activeTool.value === 'cha2') {
    return `CHA₂DS₂-VASc 评分：${cha2Score.value} 分\n请结合房颤类型、出血风险和患者意愿评估抗凝策略。`
  }
  return `HAS-BLED 评分：${hasBledScore.value} 分\n≥3 分提示出血风险较高，应加强可纠正危险因素管理，不应仅因评分高拒绝抗凝。`
})

async function copyResult() {
  await copyText(resultText.value)
  showSuccess('计算结果已复制')
}

function close() {
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="calculator-backdrop" @click.self="close">
      <aside class="calculator-drawer">
        <header>
          <div><p class="eyebrow">CLINICAL TOOLS</p><h3>临床计算器</h3></div>
          <button type="button" class="close-btn" @click="close">×</button>
        </header>

        <nav class="tool-tabs">
          <button v-for="tool in tools" :key="tool.key" type="button"
            :class="{ active: activeTool === tool.key }" @click="activeTool = tool.key">{{ tool.label }}</button>
        </nav>

        <div class="calculator-body">
          <section v-if="activeTool === 'rtpa'" class="tool-panel">
            <label>体重（kg）<input v-model.number="weight" type="number" min="1" max="250" step="0.5" /></label>
            <div class="result-grid">
              <div><span>总剂量</span><strong>{{ rtpaDose.total }} mg</strong></div>
              <div><span>10% 推注</span><strong>{{ rtpaDose.bolus }} mg</strong></div>
              <div><span>90% 静滴</span><strong>{{ rtpaDose.infusion }} mg</strong></div>
            </div>
            <p class="tool-note">按 0.9 mg/kg、最大 90 mg 计算。必须结合禁忌症、血压和影像结果复核。</p>
          </section>

          <section v-else-if="activeTool === 'window'" class="tool-panel">
            <label>最后正常时间<input v-model="onset" type="datetime-local" /></label>
            <div class="result-banner" :class="windowInfo.tone">
              <strong>{{ windowInfo.minutes ?? '--' }} 分钟</strong>
              <span>{{ windowInfo.label }}</span>
            </div>
          </section>

          <section v-else-if="activeTool === 'gcs'" class="tool-panel">
            <label>睁眼反应 E<select v-model.number="gcsEye"><option :value="4">4 自动睁眼</option><option :value="3">3 呼唤睁眼</option><option :value="2">2 疼痛刺激睁眼</option><option :value="1">1 无睁眼</option></select></label>
            <label>语言反应 V<select v-model.number="gcsVerbal"><option :value="5">5 回答切题</option><option :value="4">4 回答不切题</option><option :value="3">3 混乱语言</option><option :value="2">2 无意义声音</option><option :value="1">1 无语言反应</option></select></label>
            <label>运动反应 M<select v-model.number="gcsMotor"><option :value="6">6 遵嘱运动</option><option :value="5">5 疼痛定位</option><option :value="4">4 疼痛回缩</option><option :value="3">3 异常屈曲</option><option :value="2">2 异常伸直</option><option :value="1">1 无运动反应</option></select></label>
            <div class="result-banner success"><strong>{{ gcsTotal }} 分</strong><span>{{ gcsLabel }}</span></div>
          </section>

          <section v-else-if="activeTool === 'mrs'" class="tool-panel">
            <label>mRS 分级<select v-model.number="mrs"><option v-for="(text, score) in mrsDescriptions" :key="score" :value="score">{{ text }}</option></select></label>
            <div class="result-banner success"><strong>{{ mrs }} 分</strong><span>{{ mrsDescriptions[Number(mrs)] }}</span></div>
          </section>

          <section v-else-if="activeTool === 'cha2'" class="tool-panel">
            <label class="check-line"><input v-model="cha2.chf" type="checkbox" />充血性心力衰竭</label>
            <label class="check-line"><input v-model="cha2.hypertension" type="checkbox" />高血压</label>
            <label class="check-line"><input v-model="cha2.age75" type="checkbox" />年龄 ≥ 75 岁（2 分）</label>
            <label class="check-line"><input v-model="cha2.diabetes" type="checkbox" />糖尿病</label>
            <label class="check-line"><input v-model="cha2.stroke" type="checkbox" />卒中/TIA 史（2 分）</label>
            <label class="check-line"><input v-model="cha2.vascular" type="checkbox" />血管疾病</label>
            <label class="check-line"><input v-model="cha2.age65" type="checkbox" />年龄 65-74 岁</label>
            <label class="check-line"><input v-model="cha2.female" type="checkbox" />女性</label>
            <div class="result-banner warning"><strong>{{ cha2Score }} 分</strong><span>抗凝获益需结合出血风险和患者意愿综合评估。</span></div>
          </section>

          <section v-else class="tool-panel">
            <label class="check-line"><input v-model="hasBled.hypertension" type="checkbox" />未控制高血压</label>
            <label class="check-line"><input v-model="hasBled.renal" type="checkbox" />肾功能异常</label>
            <label class="check-line"><input v-model="hasBled.liver" type="checkbox" />肝功能异常</label>
            <label class="check-line"><input v-model="hasBled.stroke" type="checkbox" />卒中史</label>
            <label class="check-line"><input v-model="hasBled.bleeding" type="checkbox" />出血史或易出血倾向</label>
            <label class="check-line"><input v-model="hasBled.labileInr" type="checkbox" />INR 不稳定</label>
            <label class="check-line"><input v-model="hasBled.elderly" type="checkbox" />年龄 &gt; 65 岁</label>
            <label class="check-line"><input v-model="hasBled.drugs" type="checkbox" />合并抗血小板/NSAIDs</label>
            <label class="check-line"><input v-model="hasBled.alcohol" type="checkbox" />过量饮酒</label>
            <div class="result-banner warning"><strong>{{ hasBledScore }} 分</strong><span>≥3 分提示出血风险较高，应管理可纠正因素并加强随访。</span></div>
          </section>
        </div>

        <footer>
          <button type="button" class="secondary-action" @click="copyResult">复制结果</button>
          <button type="button" class="primary-action" @click="close">完成</button>
        </footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.calculator-backdrop { position: fixed; inset: 0; z-index: 145; background: rgba(15, 23, 42, .3); }
.calculator-drawer { position: absolute; right: 0; top: 0; bottom: 0; width: min(460px, 100vw); display: flex; flex-direction: column; background: var(--color-dialog-bg); border-left: 1px solid var(--color-dialog-border); box-shadow: -24px 0 70px rgba(15, 23, 42, .22); }
.calculator-drawer header { display: flex; justify-content: space-between; align-items: flex-start; padding: 18px 20px; border-bottom: 1px solid var(--color-border-item); }
.eyebrow { margin: 0 0 6px; color: var(--color-active-border); font-size: 9px; font-weight: 800; letter-spacing: .16em; }
.calculator-drawer h3 { margin: 0; color: var(--color-text-strong); font-size: 19px; }
.close-btn { border: none; background: transparent; color: var(--color-text-medium); font-size: 25px; cursor: pointer; }
.tool-tabs { display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 16px; border-bottom: 1px solid var(--color-border-item); }
.tool-tabs button { border: 1px solid var(--color-border); border-radius: 7px; background: var(--color-bg-base); color: var(--color-text-medium); padding: 6px 9px; font-size: 11px; cursor: pointer; }
.tool-tabs button.active { border-color: var(--color-active-border); background: var(--color-active-bg); color: var(--color-active-border); font-weight: 800; }
.calculator-body { flex: 1; overflow-y: auto; padding: 18px 20px; }
.tool-panel { display: flex; flex-direction: column; gap: 11px; }
.tool-panel label { display: flex; flex-direction: column; gap: 5px; color: var(--color-text-label); font-size: 11px; font-weight: 700; }
.tool-panel input[type='number'], .tool-panel input[type='datetime-local'], .tool-panel select { width: 100%; box-sizing: border-box; border: 1px solid var(--color-border); border-radius: 7px; padding: 9px 10px; background: var(--color-bg-input); color: var(--color-text-strong); font: inherit; font-size: 12px; }
.tool-panel .check-line { flex-direction: row; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 8px; background: var(--color-bg-light); color: var(--color-text-medium); font-weight: 500; }
.tool-panel .check-line input { accent-color: var(--color-active-border); }
.result-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.result-grid div { padding: 11px; border-radius: 8px; background: var(--color-bg-light); }
.result-grid span { display: block; color: var(--color-text-weak); font-size: 10px; }
.result-grid strong { display: block; margin-top: 5px; color: var(--color-text-strong); font-size: 16px; }
.result-banner { padding: 14px; border-radius: 10px; background: var(--color-bg-light); border-left: 3px solid var(--color-active-border); }
.result-banner strong { display: block; color: var(--color-text-strong); font-size: 21px; }
.result-banner span { display: block; margin-top: 6px; color: var(--color-text-medium); font-size: 12px; line-height: 1.55; }
.result-banner.success { border-left-color: var(--color-active-border); }
.result-banner.warning { border-left-color: var(--color-orange); }
.result-banner.danger { border-left-color: var(--color-red); }
.result-banner.muted { border-left-color: var(--color-border); }
.tool-note { margin: 2px 0 0; padding: 10px; border-radius: 8px; background: var(--color-badge-accent-bg); color: var(--color-text-medium); font-size: 11px; line-height: 1.6; }
.calculator-drawer footer { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--color-border-item); }
</style>
