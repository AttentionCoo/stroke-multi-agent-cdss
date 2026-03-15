<script setup>
defineOptions({ name: 'LearningWorkspace' })

defineProps({
  materials: {
    type: Array,
    default: () => [],
  },
  learningTotal: {
    type: Number,
    default: 0,
  },
  materialsLoading: {
    type: Boolean,
    default: false,
  },
  selectedMaterialId: {
    type: [Number, null],
    default: null,
  },
  materialDetail: {
    type: Object,
    default: null,
  },
  materialDetailLoading: {
    type: Boolean,
    default: false,
  },
  materialPageCount: {
    type: Number,
    default: 1,
  },
})

const query = defineModel('query', { required: true })

const emit = defineEmits(['search', 'select-material', 'page-change', 'open-material-link'])

function shortText(value, fallback = '暂无内容') {
  const text = String(value || '').trim()
  return text || fallback
}
</script>

<template>
  <section class="learning-workspace">
    <div class="material-list-card">
      <div class="section-head">
        <div>
          <h3>学习资料列表</h3>
          <p>按分类筛选医生学习资料，并查看详情。</p>
        </div>
      </div>

      <form class="toolbar" @submit.prevent="emit('search')">
        <input v-model="query.category" type="text" placeholder="例如：心血管疾病" />
        <button type="submit" class="secondary-action">查询资料</button>
      </form>

      <div v-if="materialsLoading" class="empty-card">正在加载学习资料...</div>

      <div v-else-if="materials.length" class="material-list">
        <article v-for="material in materials" :key="material.id" class="material-item"
          :class="{ active: material.id === selectedMaterialId }" @click="emit('select-material', material.id)">
          <div class="material-head">
            <h4>{{ material.title }}</h4>
            <span class="type-badge">{{ material.type || '资料' }}</span>
          </div>
          <p>{{ shortText(material.url, '点击查看详情') }}</p>
        </article>
      </div>

      <div v-else class="empty-card">暂无学习资料，请调整分类关键词后重试。</div>

      <div class="pager">
        <button type="button" class="secondary-action" :disabled="query.page <= 1"
          @click="emit('page-change', -1)">上一页</button>
        <span>第 {{ query.page }} / {{ materialPageCount }} 页，共 {{ learningTotal }} 条</span>
        <button type="button" class="secondary-action" :disabled="query.page >= materialPageCount"
          @click="emit('page-change', 1)">
          下一页
        </button>
      </div>
    </div>

    <div class="material-detail-card">
      <div class="section-head">
        <div>
          <h3>资料详情</h3>
          <p>支持查看正文或打开外部资源链接。</p>
        </div>
      </div>

      <div v-if="materialDetailLoading" class="empty-card">正在加载资料详情...</div>

      <div v-else-if="materialDetail" class="detail-card accent">
        <div class="detail-title-row">
          <div>
            <p class="summary-label">资料标题</p>
            <h4>{{ materialDetail.title }}</h4>
          </div>
          <button v-if="materialDetail.url" type="button" class="secondary-action"
            @click="emit('open-material-link', materialDetail.url)">
            打开原文
          </button>
        </div>

        <div class="material-content">
          <p>{{ shortText(materialDetail.content, '该资料未返回正文，可通过原文链接查看。') }}</p>
        </div>
      </div>

      <div v-else class="empty-card">从左侧选择一份资料后，这里会显示详情。</div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.learning-workspace {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

/* ───────────────── Panels ───────────────── */
.material-list-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid #d1e4df;
  background: #f8fbfa;
  overflow: hidden;
}

.material-detail-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #fff;
  overflow-y: auto;
}

/* ───────────────── Section / toolbar / pager ───────────────── */
.section-head,
.material-head,
.detail-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.section-head {
  padding: 10px 14px;
  border-bottom: 1px solid #e2eeeb;
  flex-shrink: 0;
}

.section-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #17313a;
}

.section-head p {
  margin: 3px 0 0;
  font-size: 13px;
  color: #5e7379;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid #e2eeeb;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.toolbar input {
  flex: 1 1 160px;
  border: 1px solid #d1e4df;
  background: #fff;
  border-radius: 6px;
  padding: 7px 10px;
  font: inherit;
  color: #17313a;
  box-sizing: border-box;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 14px;
  border-top: 1px solid #e2eeeb;
  font-size: 13px;
  color: #5e7379;
  flex-shrink: 0;
}

/* ───────────────── Buttons ───────────────── */
.secondary-action {
  border: none;
  cursor: pointer;
  transition: all 0.18s ease;
  padding: 7px 12px;
  border-radius: 7px;
  font-weight: 600;
  font-size: 14px;
  background: rgba(209, 228, 223, 0.7);
  color: #17313a;
}

/* ───────────────── Material list ───────────────── */
.material-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.material-item {
  padding: 10px 14px;
  border-bottom: 1px solid #e8f0ee;
  cursor: pointer;
  transition: background 0.15s ease;
  flex-shrink: 0;
}

.material-item:hover {
  background: rgba(17, 150, 127, 0.05);
}

.material-item.active {
  background: rgba(17, 150, 127, 0.09);
  border-left: 3px solid #11967f;
  padding-left: 11px;
}

.material-item h4 {
  margin: 0 0 3px;
  font-size: 14px;
  font-weight: 700;
  color: #17313a;
}

.material-item p {
  margin: 0;
  font-size: 13px;
  color: #5e7379;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.material-head {
  margin-bottom: 4px;
}

.type-badge {
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
  white-space: nowrap;
}

/* ───────────────── Material detail ───────────────── */
.detail-card {
  padding: 16px 20px;
  border-bottom: 1px solid #e2eeeb;
}

.detail-card.accent {
  background: rgba(17, 150, 127, 0.03);
  border-top: 3px solid #11967f;
}

.detail-title-row {
  margin-bottom: 12px;
}

.detail-title-row h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.summary-label {
  margin: 0 0 3px;
  font-size: 12px;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: #2c7c6e;
}

.material-content {
  padding: 12px 14px;
  border-left: 2px solid #d1e4df;
  background: #f8fbfa;
}

.material-content p {
  margin: 0;
  color: #5e7379;
  font-size: 14px;
  line-height: 1.6;
}

.empty-card {
  padding: 24px 16px;
  color: #9eb3ae;
  font-size: 14px;
  line-height: 1.6;
  text-align: center;
  flex-shrink: 0;
}

@media (max-width: 1080px) {
  .learning-workspace {
    grid-template-columns: 1fr;
    height: auto;
    overflow: visible;
  }

  .material-list-card {
    border-right: none;
    border-bottom: 1px solid #d1e4df;
    max-height: 340px;
    overflow: hidden;
  }
}

@media (max-width: 640px) {

  .section-head,
  .toolbar,
  .pager,
  .material-head,
  .detail-title-row {
    flex-wrap: wrap;
  }
}
</style>