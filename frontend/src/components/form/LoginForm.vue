<script setup>
import { ref } from 'vue'
import { loginAPI } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { useRouter } from 'vue-router'

const userStore = useUserStore()
const router = useRouter()

const loginFormData = ref({
  name: '',
  password: '',
})

const errorMessage = ref('')
const MAX_USERNAME_LENGTH = 15

async function handleLogin() {
  errorMessage.value = ''

  if (!loginFormData.value.name) {
    errorMessage.value = '用户名不能为空'
    return
  }
  if (loginFormData.value.name.length < 3) {
    errorMessage.value = '用户名至少为3个字符'
    return
  }
  if (loginFormData.value.name.length > MAX_USERNAME_LENGTH) {
    errorMessage.value = `用户名最多${MAX_USERNAME_LENGTH}个字符`
    return
  }
  if (!loginFormData.value.password) {
    errorMessage.value = '密码不能为空'
    return
  }
  if (loginFormData.value.password.length < 6) {
    errorMessage.value = '密码至少为6个字符'
    return
  }

  try {
    const res = await loginAPI(loginFormData.value)
    if (res.code === 1) {
      userStore.name = res.data.name
      userStore.image = res.data.image
      userStore.token = res.data.token

      // 跳转到对话
      router.replace('/')
    }
  } catch (err) {
    if (err?.code === 0) {
      errorMessage.value = '密码错误'
    } else {
      errorMessage.value = err?.msg || '登录失败，请稍后再试'
    }
  }
}
</script>

<template>
  <div class="auth-form">
    <h2>登录</h2>

    <div class="auth-input-group">
      <div class="auth-input-wrapper">
        <span class="icon">
          <UserSVG size="20" color="var(--color-text-medium)"></UserSVG>
        </span>
        <input v-model="loginFormData.name" class="auth-input" type="text" placeholder="请输入用户名"
          :maxlength="MAX_USERNAME_LENGTH"
          @keyup.enter="handleLogin" />
        <span class="auth-input-highlight"></span>
      </div>
    </div>

    <div class="auth-input-group">
      <div class="auth-input-wrapper">
        <span class="icon">
          <PasswordSVG size="20" color="var(--color-text-medium)"></PasswordSVG>
        </span>
        <input v-model="loginFormData.password" class="auth-input" type="password" placeholder="请输入密码"
          @keyup.enter="handleLogin" />
        <span class="auth-input-highlight"></span>
      </div>
    </div>

    <div v-if="errorMessage" class="auth-error">{{ errorMessage }}</div>

    <button class="primary-action auth-submit-btn" @click="handleLogin">登录</button>
  </div>
</template>
