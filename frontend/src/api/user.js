import request from '@/utils/request'

// 1. 登录
// 登录表单 = { name: 字符串, password: 字符串 }
export const loginAPI = (loginForm) => request.post('/user/login', loginForm)

// 2. 注册
// 注册表单 = { name: 字符串, password: 字符串, image: 字符串 }
export const registerAPI = (registerForm) => request.post('/user/register', registerForm)

// 3. 上传头像
// file: File 对象
export const uploadAvatarAPI = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/user/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 4. 退出登录
export const logoutAPI = () => request.post('/user/logOut')

// 5. 展示用户信息
export const getProfileAPI = () => request.get('/user/showInfo')

// 6. 修改用户信息
// 数据 = { prePassword: 字符串, newPassword: 字符串, image: 字符串 }
export const updateInfoAPI = (data) => request.put('/user/showInfo/changeKey', data)
