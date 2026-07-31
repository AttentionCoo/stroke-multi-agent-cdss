import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildClinicalSummary,
  buildEvidenceCards,
  buildPrintableAssessment,
  normalizeAssessmentPayload,
} from '../src/utils/strokeAssessment.js'

test('结构化评估表单将空值保留为未知且正确转换数值', () => {
  const payload = normalizeAssessmentPayload({
    patientId: '12',
    lastKnownWellAt: '2026-07-31T08:30',
    arrivalAt: '',
    systolicBloodPressure: '165',
    diastolicBloodPressure: '',
    bloodGlucoseMmolL: '6.2',
    nihssScore: '8',
    plateletCount: '180',
    inr: '1.1',
    anticoagulantUse: 'NO',
    anticoagulantLastDoseAt: '',
    ctHemorrhage: 'UNKNOWN',
    ctaLargeVesselOcclusion: 'NO',
    notes: '  补充信息  ',
  })

  assert.equal(payload.patientId, 12)
  assert.equal(payload.systolicBloodPressure, 165)
  assert.equal(payload.diastolicBloodPressure, null)
  assert.equal(payload.bloodGlucoseMmolL, 6.2)
  assert.equal(payload.arrivalAt, null)
  assert.equal(payload.ctHemorrhage, 'UNKNOWN')
  assert.equal(payload.notes, '补充信息')
})

test('临床摘要明确标记未知信息并带入确定性风险', () => {
  const summary = buildClinicalSummary(
    normalizeAssessmentPayload({
      patientId: '12',
      lastKnownWellAt: '2026-07-31T08:30',
      systolicBloodPressure: '190',
      diastolicBloodPressure: '115',
      anticoagulantUse: 'UNKNOWN',
      ctHemorrhage: 'UNKNOWN',
      ctaLargeVesselOcclusion: 'UNKNOWN',
      notes: '',
    }),
    {
      missingFields: ['到院时间', '头颅CT出血结论'],
      riskFlags: [{ title: '血压超过再灌注治疗复核阈值' }],
    },
    '张三',
  )

  assert.match(summary, /患者：张三/)
  assert.match(summary, /到院时间：未知/)
  assert.match(summary, /缺失信息：到院时间、头颅CT出血结论/)
  assert.match(summary, /确定性规则提示：血压超过再灌注治疗复核阈值/)
  assert.match(summary, /请基于现有多智能体流程进行分析/)
})

test('证据卡片把包含文献引用的建议与来源绑定', () => {
  const cards = buildEvidenceCards(`
## 当前建议
- 建议完善血管影像评估。《中国急性缺血性卒中诊治指南2023》
- 复核出血风险。《中国重症卒中管理指南2024》《中国急性缺血性卒中诊治指南2023》
`)

  assert.equal(cards.length, 2)
  assert.deepEqual(cards[0].sources, ['中国急性缺血性卒中诊治指南2023'])
  assert.deepEqual(cards[1].sources, ['中国重症卒中管理指南2024', '中国急性缺血性卒中诊治指南2023'])
})

test('可打印报告转义用户输入并包含审核状态', () => {
  const html = buildPrintableAssessment({
    id: 9,
    version: 2,
    status: 'REJECTED',
    data: { notes: '<script>alert(1)</script>' },
    evaluation: { completenessPercent: 80, missingFields: [], riskFlags: [] },
  })

  assert.match(html, /评估 #9/)
  assert.match(html, /REJECTED/)
  assert.doesNotMatch(html, /<script>/)
  assert.match(html, /&lt;script&gt;/)
})
