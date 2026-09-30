export function buildPatientAwareRequest(question, patientId, images = []) {
  const request = { question }
  const normalizedPatientId = Number(patientId)

  if (
    patientId !== null &&
    patientId !== undefined &&
    Number.isSafeInteger(normalizedPatientId) &&
    normalizedPatientId > 0
  ) {
    request.patientId = normalizedPatientId
  }
  if (Array.isArray(images) && images.length > 0) {
    request.images = images
  }

  return request
}

export function resolveLinkedPatientId(currentPatientId, patients = []) {
  // select 的 option value 在 DOM 中只能是字符串, 绑 null 会被渲染为 "null",
  // 因此"未关联"统一用 '' 约定; 空值/未匹配均返回 '', 与调用方的 truthy 判断兼容。
  if (!currentPatientId) return ''

  const current = Number(currentPatientId)
  const match = patients.find((patient) => Number(patient?.id) === current)
  return match ? match.id : ''
}
