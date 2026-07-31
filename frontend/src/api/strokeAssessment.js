import request from '@/utils/request'

export const evaluateStrokeAssessmentAPI = (data) =>
  request.post('/stroke-assessments/evaluate', data)

export const createStrokeAssessmentAPI = (data) =>
  request.post('/stroke-assessments', data)

export const updateStrokeAssessmentAPI = (id, data) =>
  request.put(`/stroke-assessments/${id}`, data)

export const getStrokeAssessmentsAPI = (limit = 20) =>
  request.get('/stroke-assessments', { params: { limit } })

export const getStrokeAssessmentReviewsAPI = (id) =>
  request.get(`/stroke-assessments/${id}/reviews`)

export const reviewStrokeAssessmentAPI = (id, data) =>
  request.post(`/stroke-assessments/${id}/reviews`, data)

export const exportStrokeAssessmentFhirAPI = (id) =>
  request.get(`/stroke-assessments/${id}/fhir`)
