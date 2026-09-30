import assert from 'node:assert/strict'
import test from 'node:test'

import { buildPatientAwareRequest, resolveLinkedPatientId } from '../src/utils/patientMemory.js'


test('已选择患者时在问诊请求中携带患者ID', () => {
  assert.deepEqual(buildPatientAwareRequest('突发偏瘫', '42', ['image']), {
    question: '突发偏瘫',
    patientId: 42,
    images: ['image'],
  })
})


test('未选择患者时保持原有请求格式', () => {
  assert.deepEqual(buildPatientAwareRequest('脑梗怎么办', null, []), {
    question: '脑梗怎么办',
  })
})


test('患者列表加载后保持未关联状态', () => {
  const patients = [{ id: 1 }, { id: 2 }]

  // "未关联"统一返回 ''(select option 的 value 只能是字符串, null 会被渲染为 "null")
  assert.equal(resolveLinkedPatientId(null, patients), '')
  assert.equal(resolveLinkedPatientId('', patients), '')
  assert.equal(resolveLinkedPatientId(2, patients), 2)
  assert.equal(resolveLinkedPatientId(9, patients), '')
})
