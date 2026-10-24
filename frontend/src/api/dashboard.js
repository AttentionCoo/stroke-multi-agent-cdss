import request from '@/utils/request'

export const getDashboardSummaryAPI = () => request.get('/dashboard/summary')

export const getSystemHealthAPI = () => request.get('/monitor/health')
export const getOnlineUsersAPI = () => request.get('/monitor/online-users')
export const getCacheStatsAPI = () => request.get('/monitor/cache/stats')
export const getKbStatusAPI = () => request.get('/kb/status')
