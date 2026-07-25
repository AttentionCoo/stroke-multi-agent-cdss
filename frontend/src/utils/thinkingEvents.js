function stripMarkdownText(content) {
  return content
    .replace(/\r\n?/g, '\n')
    .replace(/```[^\n]*\n?([\s\S]*?)```/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/<https?:\/\/[^>]+>/g, '')
    .replace(/<br\s*\/?\s*>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/[ \t]+#{1,6}[ \t]+/g, '\n')
    .replace(/([：:。；;])\s*[-+]\s+/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/\s+#+\s*$/gm, '')
    .replace(/^\s{0,3}>\s?/gm, '')
    .replace(/^\s*(?:[-+*]|\d+[.)])\s+/gm, '')
    .replace(/^\s*\[[ xX]\]\s+/gm, '')
    .replace(/^\s{0,3}(?:[-*_]\s*){3,}$/gm, '')
    .replace(/(\*\*|__)(.*?)\1/g, '$2')
    .replace(/~~(.*?)~~/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/(^|[^\w])\*([^*\n]+)\*(?=$|[^\w])/g, '$1$2')
    .replace(/(^|[^\w])_([^_\n]+)_(?=$|[^\w])/g, '$1$2')
    .replace(/\\([\\`*{}[\]()#+\-.!_>])/g, '$1')
    .replace(/[ \t]{2,}/g, ' ')
    .split('\n')
    .map((line) => line.trim())
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function formatStructuredValue(value) {
  if (typeof value === 'string') return stripMarkdownText(value)
  if (Array.isArray(value)) {
    return value.map(formatStructuredValue).filter(Boolean).join('\n')
  }
  if (value && typeof value === 'object') {
    return Object.entries(value)
      .map(([key, nestedValue]) => {
        const label = stripMarkdownText(key)
        const nestedText = formatStructuredValue(nestedValue)
        if (!nestedText) return label
        const [firstLine, ...remainingLines] = nestedText.split('\n')
        return [`${label}：${firstLine}`, ...remainingLines].join('\n')
      })
      .filter(Boolean)
      .join('\n')
  }
  return value == null ? '' : String(value)
}

function stripMixedStructuredText(content) {
  return content
    .replace(/^```[^\n]*$/gm, '')
    .split(/\r?\n/)
    .map((line) => {
      const trimmed = line.trim()
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        try {
          return formatStructuredValue(JSON.parse(trimmed))
        } catch {
          // 当前行不是完整 JSON，继续按普通 Markdown 文本处理。
        }
      }
      return stripMarkdownText(line)
    })
    .filter(Boolean)
    .join('\n')
}

/** 将思考内容中的 Markdown 标记转换为适合面板展示的纯文本。 */
export function stripThinkingMarkdown(content) {
  if (content == null) return ''
  if (typeof content !== 'string') return formatStructuredValue(content)

  const trimmed = content.trim()
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return formatStructuredValue(JSON.parse(trimmed))
    } catch {
      // 非法 JSON 继续按普通 Markdown 文本处理。
    }
  }
  return stripMixedStructuredText(content)
}

function normalizeThinkingEvent(thinking = {}) {
  const content = stripThinkingMarkdown(thinking.content)
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
