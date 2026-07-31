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
  if (currentPatientId === null || currentPatientId === undefined) return null

  const current = Number(currentPatientId)
  const match = patients.find((patient) => Number(patient?.id) === current)
  return match ? match.id : null
}
