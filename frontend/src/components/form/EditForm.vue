<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AvatarUpload from '../AvatarUpload.vue'
import { useUserStore } from '@/stores/user'
import { logoutAPI, updateInfoAPI } from '@/api/user'

const form$ = ref(null)
const router = useRouter()
const userStore = useUserStore()

const EditFormData = ref({
  prePassword: '',
  newPassword: ''
})
const image = ref('')

async function handleUpdateInfo() {
  await form$.value.validate()
  if (form$.value.invalid) {
    return
  }

  const updateForm = {
    prePassword: EditFormData.value.prePassword,
    newPassword: EditFormData.value.newPassword,
    image: image.value || userStore.image // 如果没有新上传头像，就用原来的
  }

  try {
    await updateInfoAPI(updateForm)
    alert('修改成功，请重新登录')
    userStore.reset()
    router.replace('/login')
  } catch (error) {
    // 说明密码错误
    console.log(error)
    alert('旧密码错误，修改失败')
  }

}

function handleAvatarUploadSuccess(url) {
  image.value = url
}


async function handleLogout() {
  await logoutAPI()
  userStore.reset()
  router.replace('/login')
}
</script>

<template>
  <Vueform validate-on="change" :display-errors="false" size="lg" v-model="EditFormData" ref="form$">

    <StaticElement name="showName">
      <p>Hi,{{ userStore.name }}</p>
    </StaticElement>


    <TextElement name="prePassword" input-type="password" placeholder="请输入旧密码" rules="required|min:6" :debounce="300"
      :messages="{
        required: '旧密码不能为空',
        min: '密码至少为6个字符',
      }">
      <template #addon-before>
        <PasswordSVG size="24" color="#fff"></PasswordSVG>
      </template>
    </TextElement>

    <TextElement name="newPassword" input-type="password" placeholder="请输入新密码" rules="required|min:6" :debounce="300"
      :messages="{
        required: '新密码不能为空',
        min: '密码至少为6个字符',
      }">
      <template #addon-before>
        <PasswordSVG size="24" color="#fff"></PasswordSVG>
      </template>
    </TextElement>

    <StaticElement name="avatar-upload">
      <div class="avatar-upload">
        <AvatarUpload :initialAvatar="userStore.image" :initialName="userStore.name"
          @uploaded="url => handleAvatarUploadSuccess(url)" />
      </div>
    </StaticElement>

    <ButtonElement name="submit" @click="handleUpdateInfo" full> 确认修改 </ButtonElement>

    <ButtonElement name="logout" @click="handleLogout" full danger> 退出登录 </ButtonElement>
  </Vueform>
</template>

<style scoped lang="scss">
.avatar-upload {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.preview img {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: 50%;
}
</style>
