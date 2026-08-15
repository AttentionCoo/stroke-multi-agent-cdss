<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import VuePdfEmbed from 'vue-pdf-embed'
// 配置 pdfjs worker（Vite 兼容写法）
import * as pdfjsLib from 'pdfjs-dist'
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.js',
  import.meta.url
).href

defineOptions({ name: 'PdfPreviewModal' })

const props = defineProps({
  visible: { type: Boolean, default: false },
  url: { type: String, default: '' },
  fileName: { type: String, default: 'document.pdf' },
  downloadUrl: { type: String, default: '' },
  // 证据页码定位: 打开后自动滚动到该页
  initialPage: { type: Number, default: 1 },
})

const emit = defineEmits(['close'])

const MAX_DOCUMENT_WIDTH = 960
const VIEWPORT_SIDE_ALLOWANCE = 56
const MIN_DOCUMENT_WIDTH = 240
const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2]

const currentPage = ref(1)
const totalPages = ref(0)
const loading = ref(true)
const zoomLevel = ref(1)
const bodyRef = ref(null)
const baseDocumentWidth = ref(MAX_DOCUMENT_WIDTH)

let resizeObserver = null
let resizeFrame = 0
let pageJumped = false

const documentWidth = computed(() => {
  return Math.max(MIN_DOCUMENT_WIDTH, Math.round(baseDocumentWidth.value * zoomLevel.value))
})

const zoomText = computed(() => `${Math.round(zoomLevel.value * 100)}%`)
const canZoomOut = computed(() => zoomLevel.value > ZOOM_LEVELS[0])
const canZoomIn = computed(() => zoomLevel.value < ZOOM_LEVELS[ZOOM_LEVELS.length - 1])

function resetState() {
  currentPage.value = 1
  totalPages.value = 0
  loading.value = true
  zoomLevel.value = 1
  pageJumped = false
}

function updateBaseDocumentWidth() {
  const viewport = bodyRef.value

  if (!viewport) return

  const availableWidth = Math.max(
    MIN_DOCUMENT_WIDTH,
    viewport.clientWidth - VIEWPORT_SIDE_ALLOWANCE
  )

  baseDocumentWidth.value = Math.min(MAX_DOCUMENT_WIDTH, availableWidth)
}

function scheduleLayoutUpdate() {
  if (resizeFrame) cancelAnimationFrame(resizeFrame)

  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = 0
    updateBaseDocumentWidth()
    updateCurrentPageFromScroll()
  })
}

function setupResizeObserver() {
  if (!bodyRef.value || resizeObserver) return

  resizeObserver = new ResizeObserver(() => {
    scheduleLayoutUpdate()
  })

  resizeObserver.observe(bodyRef.value)
}

function cleanupResizeObserver() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }

  if (resizeFrame) {
    cancelAnimationFrame(resizeFrame)
    resizeFrame = 0
  }
}

function updateCurrentPageFromScroll() {
  const viewport = bodyRef.value

  if (!viewport || !totalPages.value) return

  const pages = viewport.querySelectorAll('.vue-pdf-embed__page')

  if (!pages.length) return

  const viewportTop = viewport.getBoundingClientRect().top
  let activePage = 1

  pages.forEach((pageElement, index) => {
    const { top } = pageElement.getBoundingClientRect()

    if (top - viewportTop <= 32) {
      activePage = index + 1
    }
  })

  currentPage.value = activePage
}

function setZoomLevel(nextZoom) {
  zoomLevel.value = nextZoom
}

function zoomOut() {
  const currentIndex = ZOOM_LEVELS.indexOf(zoomLevel.value)

  if (currentIndex > 0) {
    setZoomLevel(ZOOM_LEVELS[currentIndex - 1])
  }
}

function zoomIn() {
  const currentIndex = ZOOM_LEVELS.indexOf(zoomLevel.value)

  if (currentIndex < ZOOM_LEVELS.length - 1) {
    setZoomLevel(ZOOM_LEVELS[currentIndex + 1])
  }
}

function resetZoom() {
  setZoomLevel(1)
}

// 每次弹窗打开时重置状态
watch(
  [() => props.visible, () => props.url],
  async ([visible]) => {
    if (!visible) {
      cleanupResizeObserver()
      return
    }

    resetState()
    await nextTick()
    updateBaseDocumentWidth()
    setupResizeObserver()
  },
  { immediate: true }
)

function onLoaded(pdf) {
  // vue-pdf-embed v2 的 loaded 事件传入的是 PDF 文档对象，总页数通过 numPages 取得
  totalPages.value = pdf?.numPages ?? 0
}

function onRendered() {
  loading.value = false

  nextTick(() => {
    // 证据页码定位: 打开后滚动到引用页码
    if (props.initialPage > 1 && !pageJumped) {
      pageJumped = true
      scrollToPage(props.initialPage)
      return
    }
    updateCurrentPageFromScroll()
  })
}

function scrollToPage(page) {
  const viewport = bodyRef.value
  if (!viewport) return

  const pages = viewport.querySelectorAll('.vue-pdf-embed__page')
  const target = pages[page - 1]
  if (!target) return

  const viewportTop = viewport.getBoundingClientRect().top
  const targetTop = target.getBoundingClientRect().top
  viewport.scrollTo({
    top: viewport.scrollTop + (targetTop - viewportTop) - 10,
    behavior: 'instant',
  })
  currentPage.value = page
}

function handleDownload() {
  if (props.downloadUrl) {
    window.open(props.downloadUrl, '_blank')
  }
}

function handleBackdropClick(e) {
  if (e.target === e.currentTarget) emit('close')
}

onBeforeUnmount(() => {
  cleanupResizeObserver()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="pdf-modal-backdrop" @click="handleBackdropClick">
      <div class="pdf-modal">
        <!-- 标题栏 -->
        <div class="pdf-modal-header">
          <span class="pdf-modal-title">{{ fileName }}</span>
          <div class="pdf-modal-actions">
            <button v-if="downloadUrl" type="button" class="pdf-btn" @click="handleDownload">下载</button>
            <button type="button" class="pdf-btn close" @click="emit('close')">关闭</button>
          </div>
        </div>

        <!-- PDF 渲染区 -->
        <div ref="bodyRef" class="pdf-modal-body" @scroll="updateCurrentPageFromScroll">
          <div class="pdf-document-shell">
            <div v-if="loading" class="pdf-loading">正在加载 PDF...</div>
            <VuePdfEmbed v-if="url" class="pdf-document" :source="url" :width="documentWidth" @loaded="onLoaded"
              @rendered="onRendered" />
          </div>
        </div>

        <!-- 工具栏 -->
        <div class="pdf-modal-footer">
          <span class="pdf-page-info">
            {{ totalPages ? `第 ${currentPage} / ${totalPages} 页 · 连续滚动` : '加载中...' }}
          </span>
          <div class="pdf-zoom-controls">
            <button type="button" class="pdf-btn" :disabled="!canZoomOut" @click="zoomOut">缩小</button>
            <button type="button" class="pdf-btn" @click="resetZoom">{{ zoomText }}</button>
            <button type="button" class="pdf-btn" :disabled="!canZoomIn" @click="zoomIn">放大</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.pdf-modal-backdrop {
  position: fixed;
  inset: 0;
  background: var(--color-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.pdf-modal {
  background: var(--color-dialog-bg);
  border: 1px solid var(--color-dialog-border);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  width: min(860px, 95vw);
  height: min(90vh, 900px);
  overflow: hidden;
  box-shadow: var(--shadow-dialog);
}

.pdf-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-pdf-toolbar-bg);
  flex-shrink: 0;
  gap: 12px;
}

.pdf-modal-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pdf-modal-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.pdf-modal-body {
  flex: 1;
  overflow: auto;
  background: var(--color-pdf-surface);
  padding: 16px;
  position: relative;
}

.pdf-document-shell {
  position: relative;
  width: fit-content;
  min-width: 100%;
  min-height: 100%;
  display: flex;
  justify-content: center;
  margin: 0 auto;
}

.pdf-document {
  width: fit-content;
  max-width: none;
  flex: 0 0 auto;
}

.pdf-document :deep(.vue-pdf-embed__page) {
  margin: 0 auto 16px;
  padding: 8px;
  border: 1px solid var(--color-pdf-frame-border);
  border-radius: 18px;
  background: var(--color-pdf-frame);
  box-shadow: var(--color-pdf-page-shadow);
}

.pdf-document :deep(.vue-pdf-embed__page:last-child) {
  margin-bottom: 0;
}

.pdf-document :deep(canvas) {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 12px;
  filter: var(--filter-pdf-page);
  transition: filter var(--transition-normal);
}

.pdf-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--color-text-medium);
  font-size: 14px;
  z-index: 1;
}

.pdf-modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 18px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-pdf-toolbar-bg);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.pdf-page-info {
  font-size: 14px;
  color: var(--color-text-medium);
  min-width: 160px;
}

.pdf-zoom-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pdf-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast);
}

.pdf-btn:hover:not(:disabled) {
  background: var(--color-hover-bg);
}

.pdf-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.pdf-btn.close {
  border-color: var(--color-border-light);
  color: var(--color-text-weak);
}

@media (max-width: 640px) {
  .pdf-modal {
    width: 100vw;
    height: 100vh;
    border-radius: 0;
  }

  .pdf-modal-header,
  .pdf-modal-footer {
    padding: 12px;
  }

  .pdf-modal-body {
    padding: 12px;
  }

  .pdf-modal-footer {
    justify-content: center;
  }

  .pdf-page-info {
    width: 100%;
    text-align: center;
  }
}
</style>
