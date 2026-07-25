import test from 'node:test'
import assert from 'node:assert/strict'

import { createThinkingHistorySlots, mergeThinkingEvent } from '../src/utils/thinkingEvents.js'

test('完成事件更新已有步骤，不重复添加', () => {
  const events = []

  mergeThinkingEvent(events, {
    step: 'analysis',
    title: '正在分析病例结构...',
    content: '',
    status: 'running',
  })
  mergeThinkingEvent(events, {
    step: 'analysis',
    title: '病例结构化分析',
    content: '{"复杂度":"critical"}',
    status: 'done',
  })

  assert.deepEqual(events, [
    {
      step: 'analysis',
      title: '病例结构化分析',
      content: '{"复杂度":"critical"}',
      status: 'done',
    },
  ])
})

test('反思循环中同名节点只更新最近一次执行', () => {
  const events = [
    { step: 'reason', title: '多专家临床推理', content: '第一次结果', status: 'done' },
  ]

  mergeThinkingEvent(events, {
    step: 'reason',
    title: '正在进行临床推理...',
    content: '',
    status: 'running',
  })
  mergeThinkingEvent(events, {
    step: 'reason',
    title: '多专家临床推理',
    content: '反思后的结果',
    status: 'done',
  })

  assert.equal(events.length, 2)
  assert.equal(events[0].content, '第一次结果')
  assert.equal(events[1].content, '反思后的结果')
  assert.equal(events[1].status, 'done')
})

test('缺少开始事件时仍保留完成内容', () => {
  const events = []

  mergeThinkingEvent(events, {
    step: 'retrieve',
    title: '循证医学证据检索',
    content: '检索到 3 个证据片段',
    status: 'done',
  })

  assert.equal(events.length, 1)
  assert.equal(events[0].content, '检索到 3 个证据片段')
})

test('历史回答保留空槽位以对齐后续思考记录', () => {
  const slots = createThinkingHistorySlots([
    { role: 'user', content: '问题一' },
    { role: 'assistant', content: '回答一' },
    { role: 'user', content: '问题二' },
    { role: 'assistant', content: '回答二' },
  ])

  slots.push({ events: [{ step: 'intent' }] })

  assert.deepEqual(slots, [null, null, { events: [{ step: 'intent' }] }])
})
