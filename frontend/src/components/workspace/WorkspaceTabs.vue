<script setup>
defineOptions({ name: 'WorkspaceTabs' })

defineProps({
  tabs: {
    type: Array,
    default: () => [],
  },
  activeTab: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['change'])
</script>

<template>
  <nav class="workspace-tabs" aria-label="工作台模块切换">
    <button v-for="tab in tabs" :key="tab.key" type="button" class="tab-btn" :class="{ active: tab.key === activeTab }"
      @click="emit('change', tab.key)">
      <span>{{ tab.label }}</span>
    </button>
  </nav>
</template>

<style scoped lang="scss">
.workspace-tabs {
  display: flex;
  height: 100%;
  overflow-x: auto;
}

.tab-btn {
  border: none;
  border-bottom: 2px solid transparent;
  padding: 0 18px;
  background: transparent;
  color: #5e7379;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  white-space: nowrap;
  height: 100%;

  span {
    display: block;
  }

  &:hover {
    color: #17313a;
    background: rgba(0, 0, 0, 0.03);
  }

  &.active {
    color: #11967f;
    border-bottom-color: #11967f;
    background: transparent;
  }
}
</style>
