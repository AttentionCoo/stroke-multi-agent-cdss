import request from '@/utils/request'

export const submitDoctorFeedbackAPI = (data) => request.post('/feedback', data)

export const getDoctorFeedbackSummaryAPI = () => request.get('/feedback/summary')
