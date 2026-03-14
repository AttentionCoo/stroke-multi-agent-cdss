<script setup>
import { ref } from 'vue'
import { loginAPI } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { useRouter } from 'vue-router'

const form$ = ref(null)
const userStore = useUserStore()
const router = useRouter()

const loginFormData = ref({
  name: '',
  password: '',
})

async function handleLogin() {
  await form$.value.validate()
  // 校验通过
  if (!form$.value.invalid) {
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
        alert('密码错误')
      } else {
        alert(err?.msg || '登录失败，请稍后再试')
      }
    }
  }
}
</script>

<template>
  <Vueform validate-on="change" :display-errors="false" size="lg" v-model="loginFormData" ref="form$">
    <StaticElement name="head">
      <h2>登录</h2>
    </StaticElement>

    <TextElement name="name" size="lg" placeholder="请输入用户名" rules="required|min:3|max:20" :debounce="300" :messages="{
      required: '用户名不能为空',
      min: '用户名至少为3个字符',
      max: '用户名至多为20个字符',
    }">
      <template #addon-before>
        <UserSVG size="20" color="#64748b"></UserSVG>
      </template>
    </TextElement>

    <TextElement name="password" input-type="password" placeholder="请输入密码" rules="required|min:6" :debounce="300"
      :messages="{
        required: '密码不能为空',
        min: '密码至少为6个字符',
      }">
      <template #addon-before>
        <PasswordSVG size="24" color="#64748b"></PasswordSVG>
      </template>
    </TextElement>

    <ButtonElement name="submit" full @click="handleLogin"> 登录 </ButtonElement>
  </Vueform>
</template>

<style scoped lang="scss">
h2 {
  color: #1e293b;
  margin-bottom: 1.5rem;
}

.go-register {
  color: #3b82f6;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
}
</style>
