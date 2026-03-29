<script setup>
import { computed } from 'vue'

defineOptions({ name: 'PapersSidebar' })

const props = defineProps({
  papers: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  activePaperPmid: {
    type: String,
    default: '',
  },
  searched: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['select'])

const DISPLAY_TYPES = new Set([
  'Practice Guideline',
  'Guideline',
  'Meta-Analysis',
  'Systematic Review',
  'Randomized Controlled Trial',
  'Clinical Trial',
  'Review',
  'Case Reports',
])

const isEmpty = computed(() => !props.loading && props.papers.length === 0)

function displayTypes(pubTypes) {
  return (pubTypes || []).filter((type) => DISPLAY_TYPES.has(type)).slice(0, 2)
}

function selectPaper(paper) {
  emit('select', paper)
}
</script>

<template>
  <div class="papers-sidebar">
    <div v-if="loading" class="papers-state papers-state--loading">
      <span class="spinner" />
      <span>正在检索 PubMed...</span>
    </div>

    <div v-else-if="isEmpty && !searched" class="papers-state papers-state--empty">
      输入关键词后开始检索
    </div>

    <div v-else-if="isEmpty" class="papers-state papers-state--empty">
      没有匹配结果，建议调整英文关键词或 MeSH 术语
    </div>

    <ul v-else class="paper-list">
      <li v-for="paper in papers" :key="paper.pmid">
        <button type="button" class="paper-card" :class="{ active: activePaperPmid === paper.pmid }"
          @click="selectPaper(paper)">
          <div class="paper-journal">{{ paper.journal || 'PubMed' }}</div>
          <div class="paper-title">{{ paper.title }}</div>
          <div class="paper-meta">
            {{ [paper.authors, paper.pub_date].filter(Boolean).join(' · ') || '暂无作者与日期信息' }}
          </div>
          <div v-if="displayTypes(paper.pub_type).length" class="paper-types">
            <span v-for="type in displayTypes(paper.pub_type)" :key="type" class="type-chip">{{ type }}</span>
          </div>
        </button>
      </li>
    </ul>

    <div v-if="!loading && papers.length" class="papers-footer">
      <p class="papers-disclaimer">文献仅供参考，请结合临床判断</p>
      <p class="papers-source">数据来源: PubMed, U.S. National Library of Medicine</p>
    </div>
  </div>
</template>

<style scoped lang="scss">
.papers-sidebar {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.papers-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 14px;
  font-size: 13px;
  color: var(--color-text-weak);
}

.papers-state--empty {
  line-height: 1.6;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.paper-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  list-style: none;
  margin: 0;
  padding: 0;
}

.paper-card {
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--color-border-item);
  background: transparent;
  padding: 14px;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  transition: background var(--transition-fast), box-shadow var(--transition-fast);

  &:hover {
    background: var(--color-hover-bg);
  }

  &.active {
    background: var(--color-active-bg);
    box-shadow: inset 3px 0 0 var(--color-active-border);
  }
}

.paper-journal {
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-primary-dark);
}

.paper-title {
  font-size: 14px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--color-text-strong);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.paper-meta {
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-medium);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.paper-types {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.type-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  background: var(--color-badge-status-bg);
  color: var(--color-badge-status-color);
  font-size: 10px;
  font-weight: 700;
}

.papers-footer {
  padding: 10px 14px 14px;
  border-top: 1px solid var(--color-border-light);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.papers-disclaimer,
.papers-source {
  margin: 0;
  font-size: 10px;
  color: var(--color-text-weak);
}

.papers-source {
  font-style: italic;
}
</style>
