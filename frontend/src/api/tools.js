import request from '@/utils/request'

export const getClinicalToolsAPI = () => request.get('/tools/list')

export const callClinicalToolAPI = (name, args = {}) =>
  request.post('/tools/call', { name, arguments: args })
