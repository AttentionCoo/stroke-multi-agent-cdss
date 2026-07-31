<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { registerAPI, loginAPI } from '@/api/user'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const registerFormData = ref({
  name: '',
  password: '',
  password_confirmation: '',
})

const errorMessage = ref('')
const MAX_USERNAME_LENGTH = 15

async function handleRegister() {
  errorMessage.value = ''

  if (!registerFormData.value.name) {
    errorMessage.value = '用户名不能为空'
    return
  }
  if (registerFormData.value.name.length < 3) {
    errorMessage.value = '用户名至少为3个字符'
    return
  }
  if (registerFormData.value.name.length > MAX_USERNAME_LENGTH) {
    errorMessage.value = `用户名最多${MAX_USERNAME_LENGTH}个字符`
    return
  }
  if (!registerFormData.value.password) {
    errorMessage.value = '密码不能为空'
    return
  }
  if (registerFormData.value.password.length < 6) {
    errorMessage.value = '密码至少为6个字符'
    return
  }
  if (registerFormData.value.password !== registerFormData.value.password_confirmation) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  // 组装form
  const registerAPIData = {
    name: registerFormData.value.name,
    password: registerFormData.value.password,
  }

  try {
    const res = await registerAPI(registerAPIData)
    userStore.name = res.data.name
    userStore.token = res.data.token

    // 注册后直接登录
    try {
      const loginRes = await loginAPI({
        name: registerFormData.value.name,
        password: registerFormData.value.password,
      })
      if (loginRes.code === 1) {
        userStore.name = loginRes.data.name
        userStore.image = loginRes.data.image
        userStore.token = loginRes.data.token

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
  } catch (err) {
    errorMessage.value = err?.msg || '注册失败，请稍后再试'
    return
  }
}
</script>

<template>
  <div class="auth-form">
    <h2>注册</h2>

    <div class="auth-input-group">
      <div class="auth-input-wrapper">
        <span class="icon">
          <UserSVG size="20" color="var(--color-text-medium)"></UserSVG>
        </span>
        <input v-model="registerFormData.name" class="auth-input" type="text" placeholder="请输入用户名"
          :maxlength="MAX_USERNAME_LENGTH"
          @keyup.enter="handleRegister" />
        <span class="auth-input-highlight"></span>
      </div>
    </div>

    <div class="auth-input-group">
      <div class="auth-input-wrapper">
        <span class="icon">
          <PasswordSVG size="20" color="var(--color-text-medium)"></PasswordSVG>
        </span>
        <input v-model="registerFormData.password" class="auth-input" type="password" placeholder="请输入密码"
          @keyup.enter="handleRegister" />
        <span class="auth-input-highlight"></span>
      </div>
    </div>

    <div class="auth-input-group">
      <div class="auth-input-wrapper">
        <span class="icon">
          <PasswordSVG size="20" color="var(--color-text-medium)"></PasswordSVG>
        </span>
        <input v-model="registerFormData.password_confirmation" class="auth-input" type="password" placeholder="请再次确认密码"
          @keyup.enter="handleRegister" />
        <span class="auth-input-highlight"></span>
      </div>
    </div>

    <div v-if="errorMessage" class="auth-error">{{ errorMessage }}</div>

    <button class="primary-action auth-submit-btn" @click="handleRegister">注册</button>
  </div>
</template>
