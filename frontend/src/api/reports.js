import request from '@/utils/request'

export const getReportsByTalkAPI = (talkId) => request.get(`/reports/by-talk/${talkId}`)

export const getReportAPI = (reportId) => request.get(`/reports/${reportId}`)

export const saveReportDraftAPI = (data) => request.post('/reports', data)

export const signReportAPI = (reportId, signature) =>
  request.post(`/reports/${reportId}/sign`, { signature })
