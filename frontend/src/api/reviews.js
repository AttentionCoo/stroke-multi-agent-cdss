import request from '@/utils/request'

export const getPendingReviewsAPI = (limit = 20) =>
  request.get('/clinical-reviews/pending', { params: { limit } })

export const getPendingReviewByTalkAPI = (talkId) =>
  request.get(`/clinical-reviews/by-talk/${talkId}`)
