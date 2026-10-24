import request from '@/utils/request'

export const getPatientsAPI = ({ page = 1, size = 10, filter = {} } = {}) =>
  request.get('/patients', {
    params: {
      page,
      size,
      name: filter.name || undefined,
      diseases: filter.diseases || undefined,
    },
  })

export const getPatientDetailAPI = (id) => request.get(`/patients/${id}`)

export const createPatientAPI = (data) => request.post('/patients', data)

export const updatePatientAPI = (id, data) => request.put(`/patients/${id}`, data)

export const deletePatientAPI = (id) => request.delete(`/patients/${id}`)

export const getPatientTimelineAPI = (patientId) => request.get(`/patients/${patientId}/timeline`)

export const getPatientFollowupsAPI = (patientId) => request.get(`/patients/${patientId}/followups`)

export const createPatientFollowupAPI = (patientId, data) =>
  request.post(`/patients/${patientId}/followups`, data)

export const completePatientFollowupAPI = (patientId, followupId, data) =>
  request.put(`/patients/${patientId}/followups/${followupId}/complete`, data)
