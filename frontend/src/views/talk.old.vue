<script setup>
import { onMounted, ref } from 'vue'
import UserDialog from '@/components/UserDialog.vue'
import { useUserStore } from '@/stores/user'
import { deleteChatAPI, getChatHistoryAPI, getChatTitlesAPI, newChatAPI, sendQuestionAPI } from '@/api/talk'
import LoadingModel from '@/components/LoadingModel.vue'
import SendSVG from '@/components/svg/SendSVG.vue'

defineOptions({ name: 'TalkIndex' })

const message = ref('')
const isDialogShow = ref(false)
const userStore = useUserStore()
const talkTitleList = ref([])  // 默认空数组
const inputRef = ref(null)

const currentTalkId = ref(0)       // 当前对话 ID，0 表示新对话
const currentTalkList = ref([])    // 当前对话消息列表

const canSendMessage = ref(true) // 防止重复发送

const loading = ref(false)


// 页面挂载时拉取历史对话
onMounted(async () => {
  await fetchTalkTitle()

  if (talkTitleList.value.length > 0) {
    currentTalkId.value = talkTitleList.value[0].talkId
    fetchTalkHistory(currentTalkId.value)
  }
})

// 拉取历史标题列表
async function fetchTalkTitle() {
  const res = await getChatTitlesAPI()
  if (res.data && res.data.length > 0) {
    talkTitleList.value = res.data
  }
}

// 点击切换历史对话
function handleClickTalkTitle(talkId) {
  currentTalkId.value = talkId
  fetchTalkHistory(talkId)
}

// 获取对话历史
async function fetchTalkHistory(talkId = currentTalkId.value) {
  const res = await getChatHistoryAPI(talkId)
  currentTalkList.value = res.data
}

// 点击开始新对话
function handleNewChat() {
  currentTalkId.value = 0
  currentTalkList.value = []

  // 删除已有占位
  talkTitleList.value = talkTitleList.value.filter(t => t.talkId !== 0)

  // 插入新占位标题，确保没有重复的talkId = 0后再插入
  if (!talkTitleList.value.some(t => t.talkId === 0)) {
    talkTitleList.value.unshift({ talkId: 0, title: '新对话' })
  }

  // 自动聚焦输入框
  if (inputRef.value) inputRef.value.focus()
}

// 发送消息
async function sendMessage() {
  const text = message.value.trim()
  if (text === '') return
  message.value = ''

  canSendMessage.value = false
  loading.value = true

  // 用户消息先 push
  currentTalkList.value.push(text)

  if (currentTalkId.value === 0) {
    // 新对话
    try {
      const res = await newChatAPI({ question: text })
      const { talkId, title, content } = res.data

      currentTalkId.value = talkId

      // 替换占位标题
      const index = talkTitleList.value.findIndex(t => t.talkId === 0)
      if (index !== -1) talkTitleList.value[index] = { talkId, title }
      else talkTitleList.value.unshift({ talkId, title })

      currentTalkList.value.push(content)
    } catch (err) {
      console.error('新建对话失败', err)
      currentTalkList.value.pop() // 撤回用户消息
    }
  } else {
    // 继续对话
    try {
      const res2 = await sendQuestionAPI({ talkId: currentTalkId.value, question: text })
      currentTalkList.value.push(res2.data.content)
    } catch (err) {
      console.error('发送消息失败', err)
      currentTalkList.value.pop() // 撤回用户消息
    }
  }

  canSendMessage.value = true
  loading.value = false
}

async function handleDeleteAll() {
  if (!confirm('确定要删除所有对话吗？此操作不可撤销！')) return

  if (!talkTitleList.value || talkTitleList.value.length === 0) return

  try {
    // 循环删除每个对话
    for (const talk of talkTitleList.value) {
      // 跳过占位（新对话占位 talkId = 0）
      if (talk.talkId === 0) continue
      await deleteChatAPI(talk.talkId)
    }

    // 清空前端列表和当前对话
    talkTitleList.value = []
    currentTalkList.value = []
    currentTalkId.value = 0

  } catch (err) {
    console.error('删除所有对话失败', err)
    alert('删除失败，请重试')
  }

  // 重置所有数据
  talkTitleList.value = []
  currentTalkId.value = 0
  currentTalkList.value = []


  // 拉取空列表
  fetchTalkTitle()
}

// 弹出用户信息弹窗
function handleUserClick() {
  isDialogShow.value = true
}
</script>

<template>
  <LoadingModel v-model="loading" />

  <!-- 用户信息弹窗 -->
  <UserDialog :visible="isDialogShow" @close="isDialogShow = false"></UserDialog>

  <div class="container">
    <div class="chat-history">
      <div class="new-chat" @click="handleNewChat">开始新对话</div>
      <div class="delete-chat" @click="handleDeleteAll">删除所有对话</div>
      <h3>历史记录</h3>

      <!-- 左侧展示历史对话标题列表 -->
      <div class="chat-list">
        <div v-for="talk in talkTitleList" :key="talk.talkId" class="chat-item"
          :class="{ active: talk.talkId === currentTalkId }" @click="handleClickTalkTitle(talk.talkId)">
          <span class="title">{{ talk.title }}</span>
        </div>
      </div>
    </div>

    <div class="chat-panel">
      <!-- 渲染产品名称以及用户信息 -->
      <header class="chat-header">
        <span class="title">Synapse MD</span>
        <div class="user" @click="handleUserClick">
          <img :src="userStore.image" alt="avatar" />
          <p class="username">{{ userStore.name }}</p>
        </div>
      </header>

      <!-- 对话展示区 -->
      <main class="chat-messages">
        <div class="chat-content" v-if="currentTalkList.length > 0">
          <div v-for="(msg, i) in currentTalkList" :key="i" class="message" :class="{ user: i % 2 === 0 }">
            {{ msg }}
          </div>
        </div>
        <div v-else class="empty">
          我可以帮助您什么？
        </div>
      </main>

      <!-- 输入区 -->
      <div class="input-box">
        <input type="text" ref="inputRef" placeholder="请输入您的问题" v-model="message" @keyup.enter="sendMessage" />
        <button class="send-btn" :disabled="message.trim() === '' || !canSendMessage" @click="sendMessage">
          <SendSVG color="#fff" size="24" />
        </button>
      </div>
    </div>
  </div>
</template>



<style scoped lang="scss">
* {
  color: #fff;
}

.container {
  width: 100vw;
  height: 100vh;

  display: flex;

  .chat-history {
    width: 260px;
    background-color: #181818;
    padding: 10px;
    color: #fff;

    .new-chat,
    .delete-chat {
      margin: 15px auto;
      text-align: center;
      padding: 10px;
      transition: all 0.15s ease;
      cursor: pointer;
      font-size: 14px;
    }

    .new-chat:hover {
      background-color: #303030;
      border-radius: 5px;
    }

    .delete-chat {
      color: #ff4d4f;
    }

    .delete-chat:hover {
      background-color: #303030;
      border-radius: 5px;
    }

    h3 {
      font-size: 14px;
      margin: 20px 10px 10px;
      color: #aaa;
    }

    .chat-list {
      max-height: calc(100vh - 200px);
      overflow-y: auto;

      .chat-item {
        padding: 8px 12px;
        border-radius: 5px;
        cursor: pointer;
        font-size: 14px;
        color: #ddd;
        transition: background-color 0.15s ease;

        margin-bottom: 10px;

        .title {
          display: block;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;

        }

        &:hover {
          background-color: #303030;
        }

        &.active {
          background-color: #404040;
          font-weight: 500;
        }
      }
    }
  }

  .chat-panel {
    flex: 1;
    background-color: #212121;
    display: flex;
    flex-direction: column;

    .chat-header {
      top: 0;
      left: 0;
      right: 0;
      height: 50px;
      padding: 10px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;

      background-color: transparent;
      z-index: 10;

      .title {
        font-size: 20px;
      }

      .user {
        display: flex;
        align-items: center;
        gap: 8px;

        img {
          width: 40px;
          height: 40px;
          border-radius: 50%;
        }

        .username {
          font-weight: 500;
        }
      }
    }

    .chat-messages {
      flex: 1;
      display: flex;
      justify-content: center;
      overflow-y: auto;

      overflow: auto;

      .chat-content {
        width: 65%;
        display: flex;
        flex-direction: column;
        gap: 10px;

        overflow: auto;
        scrollbar-width: thin;
        scrollbar-color: #4d4d4d #212121;

        &::-webkit-scrollbar {
          width: 10px;
        }

        &::-webkit-scrollbar-thumb:hover {
          background-color: #c0c0c1;
        }

        .message {
          padding: 10px 30px 10px 40px;
          align-self: flex-start;

          &.user {
            background-color: #07bf9b;
            border-radius: 20px;
            align-self: flex-end;
            width: 45%;
          }
        }
      }

      .empty {
        display: flex;
        justify-content: center;
        align-items: center;
        font-size: 40px;
        font-weight: 500;
      }


    }

    .input-box {
      width: 65%;
      margin: 0 auto 20px auto;
      display: flex;
      align-items: center;
      padding: 5px 10px;
      border-radius: 50px;
      background-color: #303030;
      box-sizing: border-box;

      transition: all 0.15s ease;

      &:focus-within {
        border: 2px solid #07bf9b; // 高亮边框
      }

      input {
        flex: 1;
        height: 40px;
        padding: 0 15px;
        border: none;
        outline: none;
        background-color: transparent;
        font-size: 14px;
        font-size: 16px;

        &::placeholder {
          color: #bbb;
          font-size: 16px;
        }
      }

      .send-btn {
        width: 40px;
        height: 40px;
        margin-left: 10px;
        border-radius: 50%;
        border: none;
        background-color: #07bf9b;
        color: #fff;
        font-size: 18px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        transition: all 0.15s ease;

        &:disabled {
          background-color: #4d4d4d; // 深灰色
          cursor: not-allowed;
          color: #aaa; // 字体变暗
        }
      }
    }
  }
}
</style>
