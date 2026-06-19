import service, { requestWithRetry } from './client'

/** 开始报告生成。data: { simulation_id, force_regenerate? } */
export const generateReport = (data: Record<string, unknown>): Promise<any> => {
  return requestWithRetry(() => service.post('/api/report/generate', data), 3, 1000)
}

/** 获取报告生成状态。 */
export const getReportStatus = (reportId: string): Promise<any> => {
  return service.get('/api/report/generate/status', { params: { report_id: reportId } })
}

/** 获取 Agent 日志（增量）。 */
export const getAgentLog = (reportId: string, fromLine = 0): Promise<any> => {
  return service.get(`/api/report/${reportId}/agent-log`, { params: { from_line: fromLine } })
}

/** 获取控制台日志（增量）。 */
export const getConsoleLog = (reportId: string, fromLine = 0): Promise<any> => {
  return service.get(`/api/report/${reportId}/console-log`, { params: { from_line: fromLine } })
}

/** 获取报告详情。 */
export const getReport = (reportId: string): Promise<any> => {
  return service.get(`/api/report/${reportId}`)
}

/** 与 Report Agent 对话。data: { simulation_id, message, chat_history? } */
export const chatWithReport = (data: Record<string, unknown>): Promise<any> => {
  return requestWithRetry(() => service.post('/api/report/chat', data), 3, 1000)
}
