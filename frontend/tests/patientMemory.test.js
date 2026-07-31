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

  assert.equal(resolveLinkedPatientId(null, patients), null)
  assert.equal(resolveLinkedPatientId(2, patients), 2)
  assert.equal(resolveLinkedPatientId(9, patients), null)
})
