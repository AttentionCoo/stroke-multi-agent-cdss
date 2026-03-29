<script setup>
import { ref, watch } from 'vue'
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
})

const emit = defineEmits(['close'])

const currentPage = ref(1)
const totalPages = ref(0)
const loading = ref(true)

// 每次弹窗打开时重置状态
watch(() => props.visible, (val) => {
  if (val) {
    currentPage.value = 1
    totalPages.value = 0
    loading.value = true
  }
})

function onRendered(pdf) {
  // vue-pdf-embed v2 的 loaded 事件传入的是 PDF 文档对象，总页数通过 numPages 取得
  totalPages.value = pdf?.numPages ?? 0
  loading.value = false
}

function prevPage() {
  if (currentPage.value > 1) currentPage.value--
}

function nextPage() {
  if (currentPage.value < totalPages.value) currentPage.value++
}

function handleDownload() {
  if (props.downloadUrl) {
    window.open(props.downloadUrl, '_blank')
  }
}

function handleBackdropClick(e) {
  if (e.target === e.currentTarget) emit('close')
}
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
        <div class="pdf-modal-body">
          <div class="pdf-document-shell">
            <div v-if="loading" class="pdf-loading">正在加载 PDF...</div>
            <VuePdfEmbed v-if="url" class="pdf-document" :source="url" :page="currentPage" @loaded="onRendered" />
          </div>
        </div>

        <!-- 翻页栏 -->
        <div class="pdf-modal-footer">
          <button type="button" class="pdf-btn" :disabled="currentPage <= 1" @click="prevPage">上一页</button>
          <span class="pdf-page-info">
            {{ totalPages ? `第 ${currentPage} / ${totalPages} 页` : '加载中...' }}
          </span>
          <button type="button" class="pdf-btn" :disabled="currentPage >= totalPages" @click="nextPage">下一页</button>
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
  overflow-y: auto;
  background: var(--color-pdf-surface);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  position: relative;
}

.pdf-document-shell {
  position: relative;
  width: 100%;
  min-height: 100%;
  display: flex;
  justify-content: center;
}

.pdf-document {
  width: min-content;
  max-width: 100%;
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
  max-width: 100%;
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
  justify-content: center;
  gap: 16px;
  padding: 12px 18px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-pdf-toolbar-bg);
  flex-shrink: 0;
}

.pdf-page-info {
  font-size: 14px;
  color: var(--color-text-medium);
  min-width: 120px;
  text-align: center;
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
</style>
