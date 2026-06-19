import service, { http, requestWithRetry } from './client'
import type {
  AgentLogData,
  ApiEnvelope,
  ChatData,
  ConsoleLogData,
  GenerateReportData,
  ReportProgressData,
  ReportData,
  ReportSectionsData,
  TaskData,
} from './types'

/** 开始报告生成。data: { simulation_id, force_regenerate? } */
export const generateReport = (
  data: Record<string, unknown>,
): Promise<ApiEnvelope<GenerateReportData>> =>
  requestWithRetry(() => http.post<GenerateReportData>('/api/report/generate', data), 3, 1000)

/** 获取报告生成状态。 */
export const getReportStatus = (reportId: string): Promise<ApiEnvelope<TaskData>> =>
  http.get<TaskData>('/api/report/generate/status', { params: { report_id: reportId } })

/** 获取 Agent 日志（增量）。 */
export const getAgentLog = (reportId: string, fromLine = 0): Promise<ApiEnvelope<AgentLogData>> =>
  http.get<AgentLogData>(`/api/report/${reportId}/agent-log`, { params: { from_line: fromLine } })

/** 获取控制台日志（增量）。 */
export const getConsoleLog = (
  reportId: string,
  fromLine = 0,
): Promise<ApiEnvelope<ConsoleLogData>> =>
  http.get<ConsoleLogData>(`/api/report/${reportId}/console-log`, {
    params: { from_line: fromLine },
  })

/** 获取报告详情。 */
export const getReport = (reportId: string): Promise<ApiEnvelope<ReportData>> =>
  http.get<ReportData>(`/api/report/${reportId}`)

/** 获取报告生成进度快照。 */
export const getReportProgress = (reportId: string): Promise<ApiEnvelope<ReportProgressData>> =>
  http.get<ReportProgressData>(`/api/report/${reportId}/progress`)

/** 获取已落库章节快照。 */
export const getReportSections = (reportId: string): Promise<ApiEnvelope<ReportSectionsData>> =>
  http.get<ReportSectionsData>(`/api/report/${reportId}/sections`)

/** 下载报告（Markdown）。返回 Blob，由调用方触发浏览器下载。 */
export const downloadReport = async (reportId: string): Promise<Blob> => {
  // 该端点返回文件流而非 JSON 信封，故直接用底层 axios 实例拿 blob。
  const res = (await service.get(`/api/report/${reportId}/download`, {
    responseType: 'blob',
  })) as unknown
  // service 的响应拦截器会把 AxiosResponse 解包成 response.data；
  // 若未来绕过拦截器，也兼容 AxiosResponse<Blob> 形态。
  if (res instanceof Blob) return res
  if (res && typeof res === 'object' && 'data' in res && res.data instanceof Blob) {
    return res.data
  }
  throw new Error('报告下载响应不是有效文件')
}

/** 与 Report Agent 对话。data: { simulation_id, message, chat_history? } */
export const chatWithReport = (data: Record<string, unknown>): Promise<ApiEnvelope<ChatData>> =>
  requestWithRetry(() => http.post<ChatData>('/api/report/chat', data), 3, 1000)
