<script setup>
import { computed, ref, watch } from 'vue'

defineOptions({ name: 'AppAvatar' })

const props = defineProps({
  src: {
    type: String,
    default: ''
  },
  name: {
    type: String,
    default: ''
  },
  size: {
    type: [Number, String],
    default: 32
  },
  alt: {
    type: String,
    default: 'avatar'
  }
})

const normalizedSize = computed(() => {
  if (typeof props.size === 'number') {
    return `${props.size}px`
  }

  return props.size || '32px'
})

const imageLoadFailed = ref(false)

const hasImage = computed(() => Boolean(String(props.src || '').trim()))
const shouldShowImage = computed(() => hasImage.value && !imageLoadFailed.value)

const avatarText = computed(() => {
  const value = String(props.name || '').trim()

  if (!value) {
    return '?'
  }

  return value.length > 4 ? value.slice(0, 2) : value
})

const textClass = computed(() => {
  const length = avatarText.value.length

  if (length <= 2) return 'is-short'
  if (length === 3) return 'is-medium'
  return 'is-long'
})

const avatarStyle = computed(() => ({
  width: normalizedSize.value,
  height: normalizedSize.value,
  minWidth: normalizedSize.value,
  minHeight: normalizedSize.value
}))

watch(
  () => props.src,
  () => {
    imageLoadFailed.value = false
  }
)

const handleImageError = () => {
  imageLoadFailed.value = true
}
</script>

<template>
  <div class="app-avatar" :style="avatarStyle">
    <img v-if="shouldShowImage" :src="src" :alt="alt" @error="handleImageError" />
    <span v-else class="avatar-text" :class="textClass">{{ avatarText }}</span>
  </div>
</template>

<style scoped lang="scss">
.app-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 50%;
  border: 2px solid #eff6ff;
  background: linear-gradient(135deg, #3b82f6, #14b8a6);
  color: #fff;
  user-select: none;
  flex-shrink: 0;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .avatar-text {
    width: 100%;
    padding: 0 4px;
    text-align: center;
    font-weight: 600;
    line-height: 1;
    white-space: nowrap;
    text-overflow: ellipsis;
    overflow: hidden;

    &.is-short {
      font-size: 12px;
    }

    &.is-medium {
      font-size: 10px;
    }

    &.is-long {
      font-size: 8px;
    }
  }
}
</style>
