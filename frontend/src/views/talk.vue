<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AppAvatar from '@/components/AppAvatar.vue'
import UserDialog from '@/components/UserDialog.vue'
import ChatWorkspace from '@/components/workspace/ChatWorkspace.vue'
import LearningWorkspace from '@/components/workspace/LearningWorkspace.vue'
import PatientFormDialog from '@/components/workspace/PatientFormDialog.vue'
import PatientWorkspace from '@/components/workspace/PatientWorkspace.vue'
import WorkspaceTabs from '@/components/workspace/WorkspaceTabs.vue'
import { useUserStore } from '@/stores/user'
import {
  deleteChatAPI,
  getChatHistoryAPI,
  getChatTitlesAPI,
  newChatStreamAPI,
  sendQuestionStreamAPI,
} from '@/api/talk'
import {
  createPatientAPI,
  deletePatientAPI,
  getPatientDetailAPI,
  getPatientsAPI,
  updatePatientAPI,
} from '@/api/patient'
import { getLearningMaterialDetailAPI, getLearningMaterialsAPI } from '@/api/learning'
import { analyzePatientAPI, syncTalkToPatientAPI } from '@/api/ai'

defineOptions({ name: 'TalkIndex' })

const tabs = [
  { key: 'chat', label: '智能问诊', hint: '对话与同步分析' },
  { key: 'patients', label: '患者管理', hint: '病历与AI意见' },
  { key: 'learning', label: '医生学习', hint: '资料检索与阅读' },
]

const userStore = useUserStore()

const activeTab = ref('chat')
const isDialogShow = ref(false)

const talkTitleList = ref([])
const currentTalkId = ref(0)
const currentTalkList = ref([])
const isStreaming = ref(false)
const chatLoading = ref(false)
const deleteAllLoading = ref(false)

const patientQuery = ref({ page: 1, size: 8, name: '', diseases: '' })
const patients = ref([])
const patientTotal = ref(0)
const patientsLoading = ref(false)
const selectedPatientId = ref(null)
const patientDetail = ref(null)
const patientDetailLoading = ref(false)
const patientFormVisible = ref(false)
const patientFormMode = ref('create')
const patientSubmitting = ref(false)
const patientAnalysisLoading = ref(false)
const patientAnalysisText = ref('')
const patientForm = ref({ id: null, name: '', history: '', notes: '' })

const learningQuery = ref({ category: '', page: 1, size: 8 })
const materials = ref([])
const learningTotal = ref(0)
const materialsLoading = ref(false)
const selectedMaterialId = ref(null)
const materialDetail = ref(null)
const materialDetailLoading = ref(false)

const syncPatientId = ref(null)
const syncLoading = ref(false)
const syncResult = ref(null)

const patientsLoaded = ref(false)
const materialsLoaded = ref(false)

const overlayVisible = computed(
  () => deleteAllLoading.value || patientSubmitting.value || patientAnalysisLoading.value || syncLoading.value,
)

const patientPageCount = computed(() => Math.max(1, Math.ceil(patientTotal.value / patientQuery.value.size) || 1))
const materialPageCount = computed(() => Math.max(1, Math.ceil(learningTotal.value / learningQuery.value.size) || 1))

const syncPatient = computed(() => {
  if (!syncPatientId.value) return null

  if (patientDetail.value?.id === syncPatientId.value) {
    return patientDetail.value
  }

  return patients.value.find((patient) => patient.id === syncPatientId.value) || null
})

const conversationPayload = computed(() =>
  currentTalkList.value
    .map((content, index) => ({
      role: index % 2 === 0 ? 'user' : 'assistant',
      content: String(content || '').trim(),
    }))
    .filter((item) => item.content),
)

const canSyncConversation = computed(
  () => !!syncPatientId.value && !!currentTalkId.value && conversationPayload.value.length >= 2 && !isStreaming.value,
)

const conversationPreview = computed(() => conversationPayload.value.slice(-4))

watch(activeTab, (tab) => {
  if (tab === 'patients' && !patientsLoaded.value) {
    fetchPatients()
  }

  if (tab === 'learning' && !materialsLoaded.value) {
    fetchMaterials()
  }
})

onMounted(async () => {
  await Promise.allSettled([fetchTalkTitle(), fetchPatients()])
})

function normalizeTalkTitles(payload) {
  const source = Array.isArray(payload) ? payload : Array.isArray(payload?.titles) ? payload.titles : []

  return source
    .map((item) => ({
      talkId: Number(item?.talkId ?? item?.id ?? 0),
      title: String(item?.title ?? item?.name ?? '未命名对话'),
    }))
    .filter((item) => !Number.isNaN(item.talkId))
}

function normalizeTalkHistory(payload) {
  const source = Array.isArray(payload) ? payload : Array.isArray(payload?.conversation) ? payload.conversation : []

  if (source.every((item) => typeof item === 'string')) {
    return source.map((item) => String(item || ''))
  }

  return source
    .map((item) => String(item?.content ?? item?.message ?? ''))
    .filter((item) => item !== '')
}

function normalizeAiOpinion(aiOpinion) {
  if (!aiOpinion) return null

  if (typeof aiOpinion === 'string') {
    return {
      riskLevel: '',
      suggestion: aiOpinion,
      analysisDetails: '',
      lastUpdatedAt: '',
    }
  }

  return {
    riskLevel: String(aiOpinion.riskLevel || ''),
    suggestion: String(aiOpinion.suggestion || ''),
    analysisDetails: String(aiOpinion.analysisDetails || ''),
    lastUpdatedAt: String(aiOpinion.lastUpdatedAt || ''),
  }
}

function normalizePatient(patient) {
  const aiOpinion = normalizeAiOpinion(patient?.aiOpinion)

  return {
    id: Number(patient?.id || 0),
    name: String(patient?.name || '未命名患者'),
    history: String(patient?.history || ''),
    notes: String(patient?.notes || ''),
    aiOpinion,
    aiSummary: aiOpinion?.suggestion || aiOpinion?.analysisDetails || '暂无AI建议',
  }
}

async function fetchTalkTitle() {
  try {
    const res = await getChatTitlesAPI()
    talkTitleList.value = normalizeTalkTitles(res.data)

    if (!talkTitleList.value.length) {
      currentTalkId.value = 0
      currentTalkList.value = []
      return
    }

    const preferredTalk = talkTitleList.value.find((talk) => talk.talkId === currentTalkId.value)
    const firstValidTalk = preferredTalk || talkTitleList.value.find((talk) => talk.talkId !== 0) || talkTitleList.value[0]

    currentTalkId.value = firstValidTalk.talkId
    await fetchTalkHistory(firstValidTalk.talkId)
  } catch (error) {
    console.error('获取对话标题失败', error)
  }
}

async function fetchTalkHistory(talkId = currentTalkId.value) {
  if (!talkId) {
    currentTalkList.value = []
    return
  }

  chatLoading.value = true
  isDialogShow.value = false
  try {
    const res = await getChatHistoryAPI(talkId)
    currentTalkList.value = normalizeTalkHistory(res.data)
  } catch (error) {
    console.error('获取历史对话失败', error)
    currentTalkList.value = []
  } finally {
    chatLoading.value = false
  }
}

function handleSelectTalk(talkId) {
  if (talkId === currentTalkId.value) return
  currentTalkId.value = talkId
  fetchTalkHistory(talkId)
}

function handleNewChat() {
  currentTalkId.value = 0
  currentTalkList.value = []
  talkTitleList.value = talkTitleList.value.filter((talk) => talk.talkId !== 0)
  talkTitleList.value.unshift({ talkId: 0, title: '新对话' })
}

async function handleSendMessage(text) {
  if (!text || isStreaming.value) return

  isStreaming.value = true
  currentTalkList.value.push(text)
  currentTalkList.value.push('')
  const aiIndex = currentTalkList.value.length - 1

  try {
    const finalResult =
      currentTalkId.value === 0
        ? await newChatStreamAPI({ question: text }, (chunk) => {
          currentTalkList.value[aiIndex] += chunk
        })
        : await sendQuestionStreamAPI(
          {
            talkId: currentTalkId.value,
            question: text,
          },
          (chunk) => {
            currentTalkList.value[aiIndex] += chunk
          },
        )

    const { talkId, title, content } = finalResult.data || {}

    if (typeof content === 'string') {
      currentTalkList.value[aiIndex] = content
    }

    if (currentTalkId.value === 0 && talkId) {
      currentTalkId.value = talkId
      const placeholderIndex = talkTitleList.value.findIndex((talk) => talk.talkId === 0)

      if (placeholderIndex !== -1) {
        talkTitleList.value[placeholderIndex] = { talkId, title: title || '新对话' }
      } else {
        talkTitleList.value.unshift({ talkId, title: title || '新对话' })
      }
    }

    await fetchTalkTitle()
  } catch (error) {
    console.error('发送消息失败', error)
    currentTalkList.value.splice(aiIndex, 1)
    currentTalkList.value.pop()
    alert(error?.msg || error?.message || '发送失败，请稍后再试')
  } finally {
    isStreaming.value = false
  }
}

async function handleDeleteChat(talkId) {
  if (!talkId || talkId === 0) {
    handleNewChat()
    return
  }

  if (!window.confirm('确定要删除此对话吗？')) return

  try {
    await deleteChatAPI(talkId)
    talkTitleList.value = talkTitleList.value.filter((talk) => talk.talkId !== talkId)

    if (currentTalkId.value === talkId) {
      const nextTalk = talkTitleList.value.find((talk) => talk.talkId !== 0)
      currentTalkId.value = nextTalk?.talkId || 0
      if (nextTalk) {
        await fetchTalkHistory(nextTalk.talkId)
      } else {
        handleNewChat()
      }
    }
  } catch (error) {
    console.error('删除对话失败', error)
    alert(error?.msg || '删除失败')
  }
}

async function handleDeleteAll() {
  const ids = talkTitleList.value.map((talk) => talk.talkId).filter((talkId) => talkId !== 0)
  if (!ids.length) return
  if (!window.confirm('确定删除所有历史对话吗？')) return

  deleteAllLoading.value = true
  try {
    await Promise.all(ids.map((talkId) => deleteChatAPI(talkId)))
    talkTitleList.value = []
    handleNewChat()
  } catch (error) {
    console.error('清空对话失败', error)
    alert(error?.msg || '删除失败，请重试')
  } finally {
    deleteAllLoading.value = false
  }
}

async function fetchPatients() {
  patientsLoading.value = true

  try {
    const res = await getPatientsAPI({
      page: patientQuery.value.page,
      size: patientQuery.value.size,
      filter: {
        name: patientQuery.value.name.trim(),
        diseases: patientQuery.value.diseases.trim(),
      },
    })

    const list = Array.isArray(res.data?.patients) ? res.data.patients : []
    patients.value = list.map(normalizePatient)
    patientTotal.value = Number(res.data?.total || 0)
    patientsLoaded.value = true

    if (!patients.value.length) {
      selectedPatientId.value = null
      patientDetail.value = null
      syncPatientId.value = null
      return
    }

    if (!syncPatientId.value || !patients.value.some((patient) => patient.id === syncPatientId.value)) {
      syncPatientId.value = patients.value[0].id
    }

    const preferredId =
      selectedPatientId.value && patients.value.some((patient) => patient.id === selectedPatientId.value)
        ? selectedPatientId.value
        : patients.value[0].id

    if (activeTab.value === 'patients' || !patientDetail.value || patientDetail.value.id !== preferredId) {
      await handleSelectPatient(preferredId)
    }
  } catch (error) {
    console.error('获取患者列表失败', error)
    alert(error?.msg || '获取患者列表失败')
  } finally {
    patientsLoading.value = false
  }
}

async function handleSelectPatient(patientId) {
  if (!patientId) return

  selectedPatientId.value = patientId
  patientDetailLoading.value = true

  try {
    const res = await getPatientDetailAPI(patientId)
    patientDetail.value = normalizePatient(res.data)
  } catch (error) {
    console.error('获取患者详情失败', error)
    alert(error?.msg || '获取患者详情失败')
  } finally {
    patientDetailLoading.value = false
  }
}

function resetPatientForm() {
  patientForm.value = { id: null, name: '', history: '', notes: '' }
}

function openCreatePatient() {
  patientFormMode.value = 'create'
  resetPatientForm()
  patientFormVisible.value = true
}

function openEditPatient(patient) {
  patientFormMode.value = 'edit'
  patientForm.value = {
    id: patient.id,
    name: patient.name,
    history: patient.history,
    notes: patient.notes,
  }
  patientFormVisible.value = true
}

async function submitPatientForm() {
  const payload = {
    name: patientForm.value.name.trim(),
    history: patientForm.value.history.trim(),
    notes: patientForm.value.notes.trim(),
  }

  if (!payload.name) {
    alert('患者姓名不能为空')
    return
  }

  patientSubmitting.value = true

  try {
    if (patientFormMode.value === 'edit' && patientForm.value.id) {
      await updatePatientAPI(patientForm.value.id, payload)
      selectedPatientId.value = patientForm.value.id
    } else {
      const res = await createPatientAPI(payload)
      selectedPatientId.value = Number(res.data?.id || selectedPatientId.value)
    }

    patientFormVisible.value = false
    resetPatientForm()
    await fetchPatients()

    if (selectedPatientId.value) {
      await handleSelectPatient(selectedPatientId.value)
    }
  } catch (error) {
    console.error('保存患者失败', error)
    alert(error?.msg || '保存患者失败')
  } finally {
    patientSubmitting.value = false
  }
}

async function handleDeletePatient(patientId) {
  if (!window.confirm('确定删除该患者吗？')) return

  try {
    await deletePatientAPI(patientId)

    if (selectedPatientId.value === patientId) {
      selectedPatientId.value = null
      patientDetail.value = null
    }

    if (syncPatientId.value === patientId) {
      syncPatientId.value = null
    }

    await fetchPatients()
  } catch (error) {
    console.error('删除患者失败', error)
    alert(error?.msg || '删除患者失败')
  }
}

async function handleAnalyzePatient() {
  if (!selectedPatientId.value) {
    alert('请先选择患者')
    return
  }

  const data = patientAnalysisText.value.trim()
  if (!data) {
    alert('请输入需要提交给AI的补充健康数据')
    return
  }

  patientAnalysisLoading.value = true

  try {
    const res = await analyzePatientAPI({
      patientId: selectedPatientId.value,
      data,
    })

    patientDetail.value = {
      ...(patientDetail.value || {}),
      id: selectedPatientId.value,
      name: patientDetail.value?.name || '',
      history: patientDetail.value?.history || '',
      notes: patientDetail.value?.notes || '',
      aiOpinion: normalizeAiOpinion(res.data),
      aiSummary: res.data?.suggestion || res.data?.analysisDetails || '暂无AI建议',
    }

    patientAnalysisText.value = ''
    await fetchPatients()
    await handleSelectPatient(selectedPatientId.value)
    alert('AI分析已更新')
  } catch (error) {
    console.error('AI分析失败', error)
    alert(error?.msg || 'AI分析失败')
  } finally {
    patientAnalysisLoading.value = false
  }
}

async function fetchMaterials() {
  materialsLoading.value = true

  try {
    const res = await getLearningMaterialsAPI({
      category: learningQuery.value.category.trim(),
      page: learningQuery.value.page,
      size: learningQuery.value.size,
    })

    materials.value = Array.isArray(res.data?.materials) ? res.data.materials : []
    learningTotal.value = Number(res.data?.total || 0)
    materialsLoaded.value = true

    if (!materials.value.length) {
      selectedMaterialId.value = null
      materialDetail.value = null
      return
    }

    const preferredId = materials.value.some((item) => item.id === selectedMaterialId.value)
      ? selectedMaterialId.value
      : materials.value[0].id

    await handleSelectMaterial(preferredId)
  } catch (error) {
    console.error('获取学习资料失败', error)
    alert(error?.msg || '获取学习资料失败')
  } finally {
    materialsLoading.value = false
  }
}

async function handleSelectMaterial(materialId) {
  if (!materialId) return

  selectedMaterialId.value = materialId
  materialDetailLoading.value = true

  try {
    const res = await getLearningMaterialDetailAPI(materialId)
    materialDetail.value = res.data || null
  } catch (error) {
    console.error('获取资料详情失败', error)
    alert(error?.msg || '获取资料详情失败')
  } finally {
    materialDetailLoading.value = false
  }
}

function openMaterialLink(value) {
  if (!value) return
  window.open(value, '_blank', 'noopener,noreferrer')
}

async function handleSyncConversation() {
  if (!canSyncConversation.value) {
    alert('请先选择患者，并确保当前对话已经生成回答')
    return
  }

  if (!window.confirm('确认将当前对话同步到患者AI分析吗？')) return

  syncLoading.value = true

  try {
    const res = await syncTalkToPatientAPI({
      patientId: syncPatientId.value,
      talkId: currentTalkId.value,
      conversation: conversationPayload.value,
      mergeWithHistory: true,
    })

    syncResult.value = res.data || null
    await fetchPatients()

    if (selectedPatientId.value === syncPatientId.value || !selectedPatientId.value) {
      selectedPatientId.value = syncPatientId.value
      await handleSelectPatient(syncPatientId.value)
    }

    alert('同步完成，患者AI意见已更新')
  } catch (error) {
    console.error('同步对话失败', error)
    alert(error?.msg || '同步失败')
  } finally {
    syncLoading.value = false
  }
}

function handlePatientSearch() {
  patientQuery.value.page = 1
  fetchPatients()
}

function goPatientPage(delta) {
  const nextPage = patientQuery.value.page + delta
  if (nextPage < 1 || nextPage > patientPageCount.value) return
  patientQuery.value.page = nextPage
  fetchPatients()
}

function handleMaterialSearch() {
  learningQuery.value.page = 1
  fetchMaterials()
}

function goMaterialPage(delta) {
  const nextPage = learningQuery.value.page + delta
  if (nextPage < 1 || nextPage > materialPageCount.value) return
  learningQuery.value.page = nextPage
  fetchMaterials()
}

function openPatientWorkspace(patientId) {
  activeTab.value = 'patients'
  if (patientId) {
    handleSelectPatient(patientId)
  }
}
</script>

<template>
  <div class="workspace-shell">
    <div v-if="overlayVisible" class="page-overlay">
      <div class="overlay-card">
        <div class="spinner"></div>
        <p>正在处理，请稍候...</p>
      </div>
    </div>


    <section class="tab-section">
      <WorkspaceTabs :tabs="tabs" :active-tab="activeTab" @change="activeTab = $event" />
      <div class="user-anchor" @click="isDialogShow = !isDialogShow">
        <AppAvatar class="avatar" :src="userStore.image" :name="userStore.name" :size="24" alt="avatar" />
        <p class="user-name">{{ userStore.name || '医生' }}</p>
        <UserDialog :visible="isDialogShow" @close="isDialogShow = false" />
      </div>
    </section>

    <main class="workspace-content">
      <ChatWorkspace v-if="activeTab === 'chat'" v-model:sync-patient-id="syncPatientId"
        :talk-title-list="talkTitleList" :current-talk-id="currentTalkId" :current-talk-list="currentTalkList"
        :is-streaming="isStreaming" :chat-loading="chatLoading" :patients="patients" :sync-patient="syncPatient"
        :conversation-preview="conversationPreview" :can-sync-conversation="canSyncConversation"
        :sync-result="syncResult" @select-talk="handleSelectTalk" @new-chat="handleNewChat"
        @delete-chat="handleDeleteChat" @delete-all="handleDeleteAll" @send-message="handleSendMessage"
        @sync-conversation="handleSyncConversation" @open-patient-workspace="openPatientWorkspace" />

      <PatientWorkspace v-else-if="activeTab === 'patients'" v-model:query="patientQuery"
        v-model:analysis-text="patientAnalysisText" :patients="patients" :patient-total="patientTotal"
        :patients-loading="patientsLoading" :selected-patient-id="selectedPatientId" :patient-detail="patientDetail"
        :patient-detail-loading="patientDetailLoading" :patient-page-count="patientPageCount"
        @search="handlePatientSearch" @select-patient="handleSelectPatient" @open-create="openCreatePatient"
        @open-edit="openEditPatient" @delete-patient="handleDeletePatient" @analyze-patient="handleAnalyzePatient"
        @page-change="goPatientPage" />

      <LearningWorkspace v-else v-model:query="learningQuery" :materials="materials" :learning-total="learningTotal"
        :materials-loading="materialsLoading" :selected-material-id="selectedMaterialId"
        :material-detail="materialDetail" :material-detail-loading="materialDetailLoading"
        :material-page-count="materialPageCount" @search="handleMaterialSearch" @select-material="handleSelectMaterial"
        @page-change="goMaterialPage" @open-material-link="openMaterialLink" />
    </main>

    <PatientFormDialog v-model:form="patientForm" :visible="patientFormVisible" :mode="patientFormMode"
      @close="patientFormVisible = false" @submit="submitPatientForm" />
  </div>
</template>

<style scoped lang="scss">
:global(body) {
  margin: 0;
  background: #fff;
}

.workspace-shell {
  height: 100dvh;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  color: #17313a;
  background: #fff;
}

.tab-section {
  height: 52px;
  padding: 0 20px;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 0;
  border-bottom: 1px solid #d1e4df;
  background: #fff;
  flex-shrink: 0;
}

.workspace-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.user-anchor {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding: 0 12px;
  margin: 6px 0;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.18s ease;

  &:hover {
    background: rgba(0, 0, 0, 0.05);
  }
}

.user-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.user-anchor small {
  color: #5e7379;
  font-size: 12px;
}

.page-overlay {
  position: fixed;
  inset: 0;
  background: rgba(16, 38, 44, 0.32);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.overlay-card {
  width: 220px;
  padding: 28px 22px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 8px 32px rgba(15, 65, 79, 0.18);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.overlay-card p {
  color: #5e7379;
  margin: 0;
  font-size: 14px;
}

.spinner {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 3px solid rgba(17, 150, 127, 0.15);
  border-top-color: #11967f;
  animation: rotate 0.9s linear infinite;
}

@keyframes rotate {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 960px) {
  .tab-section {
    height: 44px;
  }

  .user-name {
    display: none;
  }

  .workspace-content {
    overflow-y: auto;
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
  }

  .user-anchor {
    margin: 0;
  }
}
</style>
