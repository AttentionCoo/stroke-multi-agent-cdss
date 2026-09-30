<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { logoutAPI, updateInfoAPI } from '@/api/user'
import AvatarUpload from './AvatarUpload.vue'
import { showError, showSuccess, showWarning } from '@/utils/feedback'

const props = defineProps({
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['close'])

const router = useRouter()
const userStore = useUserStore()
const menuRef = ref(null)

const isPasswordDialogVisible = ref(false)
const isAvatarDialogVisible = ref(false)

const passwordForm = ref({
  prePassword: '',
  newPassword: ''
})
const image = ref(userStore.image || '')

watch(
  () => userStore.image,
  (value) => {
    image.value = value || ''
  }
)

const closeMenu = () => {
  emit('close')
}

const handleGlobalClick = (event) => {
  if (!props.visible) return
  if (!menuRef.value) return
  if (menuRef.value.contains(event.target)) return
  closeMenu()
}

onMounted(() => {
  document.addEventListener('mousedown', handleGlobalClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleGlobalClick)
})

const openPasswordDialog = () => {
  isPasswordDialogVisible.value = true
  closeMenu()
}

const openAvatarDialog = () => {
  image.value = userStore.image || ''
  isAvatarDialogVisible.value = true
  closeMenu()
}

const handleAvatarUploadSuccess = (url) => {
  image.value = url
}

const performLogout = async () => {
  try {
    await logoutAPI()
  } catch (error) {
    console.error('退出登录失败，执行本地登出', error)
  } finally {
    userStore.reset()
    router.replace('/login')
  }
}

const handleLogout = async () => {
  closeMenu()
  await performLogout()
}

const handleChangePassword = async () => {
  const prePassword = String(passwordForm.value.prePassword || '').trim()
  const newPassword = String(passwordForm.value.newPassword || '').trim()

  if (prePassword.length < 6 || newPassword.length < 6) {
    showWarning('旧密码和新密码至少为6位')
    return
  }

  try {
    await updateInfoAPI({
      prePassword,
      newPassword,
      image: userStore.image || ''
    })
    showSuccess('密码修改成功，请重新登录')
    isPasswordDialogVisible.value = false
    passwordForm.value.prePassword = ''
    passwordForm.value.newPassword = ''
    await performLogout()
  } catch (error) {
    console.error('修改密码失败', error)
    showError('旧密码错误或修改失败')
  }
}

const handleChangeAvatar = async () => {
  if (!image.value) {
    showWarning('请先上传头像')
    return
  }

  try {
    await updateInfoAPI({
      prePassword: '',
      newPassword: '',
      image: image.value
    })
    userStore.image = image.value
    showSuccess('头像修改成功')
    isAvatarDialogVisible.value = false
  } catch (error) {
    console.error('修改头像失败', error)
    showError('头像修改失败，请稍后重试')
  }
}
</script>

<template>
  <transition name="fade-slide">
    <div v-if="visible" ref="menuRef" class="user-menu" @click.stop>
      <button type="button" class="menu-item" @click="openPasswordDialog">修改密码</button>
      <button type="button" class="menu-item" @click="openAvatarDialog">修改头像</button>
      <button type="button" class="menu-item danger" @click="handleLogout">退出登录</button>
    </div>
  </transition>

  <transition name="fade">
    <div v-if="isPasswordDialogVisible" class="dialog-overlay" @click.self="isPasswordDialogVisible = false">
      <div class="dialog-card" @click.stop>
        <div class="dialog-header">
          <h3>修改密码</h3>
          <button type="button" class="close-btn" @click="isPasswordDialogVisible = false">&times;</button>
        </div>

        <div class="dialog-body">
          <label>
            旧密码
            <input v-model="passwordForm.prePassword" type="password" placeholder="请输入旧密码" />
          </label>
          <label>
            新密码
            <input v-model="passwordForm.newPassword" type="password" placeholder="请输入新密码" />
          </label>
        </div>

        <div class="dialog-footer">
          <button type="button" class="plain-btn" @click="isPasswordDialogVisible = false">取消</button>
          <button type="button" class="primary-btn" @click="handleChangePassword">确认修改</button>
        </div>
      </div>
    </div>
  </transition>

  <transition name="fade">
    <div v-if="isAvatarDialogVisible" class="dialog-overlay" @click.self="isAvatarDialogVisible = false">
      <div class="dialog-card" @click.stop>
        <div class="dialog-header">
          <h3>修改头像</h3>
          <button type="button" class="close-btn" @click="isAvatarDialogVisible = false">&times;</button>
        </div>

        <div class="dialog-body avatar-body">
          <AvatarUpload :initialAvatar="image" :initialName="userStore.name" @uploaded="handleAvatarUploadSuccess" />
        </div>

        <div class="dialog-footer">
          <button type="button" class="plain-btn" @click="isAvatarDialogVisible = false">取消</button>
          <button type="button" class="primary-btn" @click="handleChangeAvatar">保存头像</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style lang="scss" scoped>
.user-menu {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: 160px;
  background: var(--color-bg-base);
  border-radius: 10px;
  border: 1px solid var(--color-menu-border);
  box-shadow: var(--shadow-menu);
  padding: 6px;
  z-index: 40;

  &::before {
    content: '';
    position: absolute;
    top: -6px;
    right: 18px;
    width: 10px;
    height: 10px;
    border-top: 1px solid var(--color-menu-border);
    border-left: 1px solid var(--color-menu-border);
    background: var(--color-bg-base);
    transform: rotate(45deg);
  }

  .menu-item {
    width: 100%;
    border: none;
    background: transparent;
    text-align: left;
    padding: 10px 12px;
    border-radius: var(--radius-md);
    cursor: pointer;
    font-size: 14px;
    color: var(--color-menu-item);
    transition: all var(--transition-fast);

    &:hover {
      background: var(--color-menu-item-hover-bg);
      color: var(--color-menu-item-hover);
    }

    &.danger {
      color: var(--color-red);

      &:hover {
        background: var(--color-menu-danger-hover-bg);
      }
    }
  }
}

.dialog-overlay {
  z-index: 90;
  background: var(--color-overlay-bg);
}

.dialog-card {
  width: min(92vw, 420px);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-dialog);
  border: 1px solid var(--color-menu-border);
  overflow: hidden;
  background: var(--color-dialog-bg);

  .dialog-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 18px;
    border-bottom: 1px solid var(--color-menu-border);

    h3 {
      margin: 0;
      font-size: 17px;
      color: var(--color-text-strong);
    }

    .close-btn {
      border: none;
      background: transparent;
      font-size: 22px;
      line-height: 1;
      color: var(--color-text-medium);
      cursor: pointer;

      &:hover {
        color: var(--color-menu-item-hover);
      }
    }
  }

  .dialog-body {
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;

    label {
      display: flex;
      flex-direction: column;
      gap: 8px;
      color: var(--color-menu-item);
      font-size: 14px;
    }

    input {
      height: 40px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      padding: 0 12px;
      font-size: 14px;
      color: var(--color-text-strong);
      background: var(--color-bg-input);

      &:focus {
        outline: none;
        border-color: var(--color-primary);
        box-shadow: 0 0 0 3px rgba(17, 150, 127, 0.15);
      }
    }

    &.avatar-body {
      align-items: center;
    }
  }

  .dialog-footer {
    padding: 14px 18px 18px;
    display: flex;
    justify-content: flex-end;
    gap: 10px;

    button {
      border: none;
      border-radius: var(--radius-md);
      padding: 8px 14px;
      cursor: pointer;
      font-size: 14px;
      transition: all var(--transition-fast);
    }

    .plain-btn {
      background: var(--color-plain-btn-bg);
      color: var(--color-plain-btn);

      &:hover {
        background: var(--color-plain-btn-hover-bg);
      }
    }

    .primary-btn {
      background: var(--color-primary-gradient);
      color: #fff;

      &:hover {
        opacity: 0.88;
      }
    }
  }
}
</style>
