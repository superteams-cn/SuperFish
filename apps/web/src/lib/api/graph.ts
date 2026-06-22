import { http, requestWithRetry } from './client'
import type { ApiEnvelope, BuildGraphResult, GraphData, ProjectData, TaskData } from './types'

/** 生成本体（上传文档和模拟需求），FormData 形式。 */
export function generateOntology(formData: FormData): Promise<ApiEnvelope<ProjectData>> {
  return requestWithRetry(() =>
    http.post<ProjectData>('/api/graph/ontology/generate', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  )
}

/** 构建图谱。 */
export function buildGraph(data: Record<string, unknown>): Promise<ApiEnvelope<BuildGraphResult>> {
  return requestWithRetry(() => http.post<BuildGraphResult>('/api/graph/build', data))
}

/** 查询任务状态。 */
export function getTaskStatus(taskId: string): Promise<ApiEnvelope<TaskData>> {
  return http.get<TaskData>(`/api/graph/task/${taskId}`)
}

/** 获取图谱数据。 */
export function getGraphData(graphId: string): Promise<ApiEnvelope<GraphData>> {
  return http.get<GraphData>(`/api/graph/data/${graphId}`)
}

/** 获取项目信息。 */
export function getProject(projectId: string): Promise<ApiEnvelope<ProjectData>> {
  return http.get<ProjectData>(`/api/graph/project/${projectId}`)
}

/** 删除项目（连同图谱/模拟/报告等关联数据）。 */
export function deleteProject(projectId: string): Promise<ApiEnvelope<{ message?: string }>> {
  return http.delete<{ message?: string }>(`/api/graph/project/${projectId}`)
}

/** 项目名额：上限 / 已用 / 剩余。用于「开始预测」前提醒与拦截。 */
export interface ProjectQuota {
  limit: number
  used: number
  available: number
}
export function getProjectQuota(): Promise<ApiEnvelope<ProjectQuota>> {
  return http.get<ProjectQuota>('/api/graph/project/quota')
}
