import request from '@/utils/request'

export const globalSearchAPI = (q) => request.get('/search', { params: { q } })
