function normalizeThinkingEvent(thinking = {}) {
  const content = thinking.content || ''
  return {
    step: thinking.step || '',
    title: thinking.title || thinking.step || 'AI 思考中...',
    content,
    status: thinking.status || (content ? 'done' : 'running'),
  }
}

/**
 * 将节点完成事件合并到最近一次同节点的执行记录。
 * 反思循环会再次执行同名节点，因此只匹配尚未完成的记录。
 */
export function mergeThinkingEvent(events, thinking) {
  const next = normalizeThinkingEvent(thinking)

  if (next.status === 'done' && next.step) {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const current = events[index]
      if (current.step === next.step && current.status !== 'done') {
        Object.assign(current, next)
        return current
      }
    }

    const last = events[events.length - 1]
    if (last?.step === next.step && last.status === 'done' && last.content === next.content) {
      Object.assign(last, next)
      return last
    }
  }

  events.push(next)
  return next
}

export function createThinkingHistorySlots(messages = []) {
  return messages.filter((message) => message?.role === 'assistant').map(() => null)
}
