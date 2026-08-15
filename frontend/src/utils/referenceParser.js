/**
 * 文献引用解析工具
 * 用于在 Markdown 渲染前，将《书名》格式的文献引用包裹成可点击的 span，
 * 供 ChatWorkspace 的事件委托机制捕获并触发 OSS 文档匹配。
 */

/**
 * 将原始文本中的《文献名》替换为带 data-ref-name 属性的 span
 * 替换后内容作为 HTML 传入 marked.parse，利用 marked 的 inline HTML 直通特性保留 span
 *
 * @param {string} raw - AI 回复的原始文本
 * @returns {string}  - 预处理后的文本（含内联 HTML span）
 */
export function injectRefLinks(raw) {
  if (!raw || typeof raw !== 'string') return raw

  // 《文献名》 + 可选页码标记(p.7 / 第7页) → 携带 data-ref-page 的点击 span
  return raw.replace(/《([^》\n]+)》(?:\s*[pP]\.?\s*(\d{1,4})|\s*第\s*(\d{1,4})\s*页)?/g, (match, name, pageDot, pageCn) => {
    // 对 data 属性值中的双引号转义，避免破坏 HTML 结构
    const safeAttr = name.replace(/"/g, '&quot;')
    const page = pageDot || pageCn || ''
    const pageAttr = page ? ` data-ref-page="${page}"` : ''
    return `<span class="ref-link" data-ref-name="${safeAttr}"${pageAttr}>${match}</span>`
  })
}
