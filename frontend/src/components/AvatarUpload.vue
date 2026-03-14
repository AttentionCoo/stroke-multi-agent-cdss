<script setup>
import { ref, watch } from 'vue'
import AppAvatar from '@/components/AppAvatar.vue'
import request from '@/utils/request'

// props: showTip 控制是否显示红色提示, initialAvatar 传入初始头像地址
const props = defineProps({
  showTip: {
    type: Boolean,
    default: false
  },
  initialAvatar: {
    type: String,
    default: '' // 如果没传，就为空字符串
  },
  initialName: {
    type: String,
    default: ''
  }
})

// emit: 上传完成后触发 uploaded 事件，传递图片地址
const emit = defineEmits(['uploaded'])

const avatarUrl = ref(props.initialAvatar) // 初始化时直接赋值一次
const fileInput = ref(null)

watch(
  () => props.initialAvatar,
  (value) => {
    avatarUrl.value = value || ''
  }
)


const triggerUpload = () => {
  fileInput.value.click()
}

const handleFileChange = async (e) => {
  const file = e.target.files[0]
  if (!file) return

  // 校验图片格式
  const validTypes = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
  if (!validTypes.includes(file.type)) {
    alert('请选择 jpg / png / webp 格式的图片')
    return
  }

  // 构造 FormData
  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await request.post('/user/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (res.code === 1) {
      avatarUrl.value = res.data // 阿里云 OSS 返回的图片地址
      emit('uploaded', avatarUrl.value) // 上传完成触发事件
    } else {
      alert('上传失败')
    }
  } catch (err) {
    console.error(err)
    alert('上传出错')
  } finally {
    e.target.value = '' // 重置 input，确保能重复选择同一文件
  }
}
</script>


<template>
  <div class="avatar-upload">
    <div class="avatar-preview" @click="triggerUpload">
      <AppAvatar :src="avatarUrl" :name="props.initialName" :size="120" alt="avatar" />
      <div class="avatar-overlay">更换头像</div>
    </div>

    <!-- 红色提示 -->
    <div v-if="props.showTip && !avatarUrl" class="tip-text">请选择图片！</div>

    <input type="file" ref="fileInput" class="file-input" accept="image/*" @change="handleFileChange" />
  </div>
</template>

<style scoped lang="scss">
.avatar-upload {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #64748b;

  .file-input {
    display: none;
  }

  .tip-text {
    margin-top: 8px;
    color: #ef4444;
    font-size: 14px;
  }

  .avatar-preview {
    position: relative;
    width: 120px;
    height: 120px;
    cursor: pointer;

    :deep(.app-avatar) {
      width: 120px !important;
      height: 120px !important;
      border: 2px solid #3b82f6;
    }

    :deep(.avatar-text.is-short) {
      font-size: 36px;
    }

    :deep(.avatar-text.is-medium) {
      font-size: 28px;
    }

    :deep(.avatar-text.is-long) {
      font-size: 22px;
    }

    .avatar-overlay {
      position: absolute;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 30%;
      background: rgba(0, 0, 0, 0.6);
      color: #fff;
      font-size: 12px;
      display: flex;
      justify-content: center;
      align-items: center;
      opacity: 0;
      transition: opacity 0.2s;
    }

    &:hover .avatar-overlay {
      opacity: 1;
    }
  }
}
</style>
