import service, { requestWithRetry } from './client'

/** 生成本体（上传文档和模拟需求），FormData 形式。 */
export function generateOntology(formData: FormData): Promise<any> {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  )
}

/** 构建图谱。 */
export function buildGraph(data: Record<string, unknown>): Promise<any> {
  return requestWithRetry(() => service({ url: '/api/graph/build', method: 'post', data }))
}

/** 查询任务状态。 */
export function getTaskStatus(taskId: string): Promise<any> {
  return service({ url: `/api/graph/task/${taskId}`, method: 'get' })
}

/** 获取图谱数据。 */
export function getGraphData(graphId: string): Promise<any> {
  return service({ url: `/api/graph/data/${graphId}`, method: 'get' })
}

/** 获取项目信息。 */
export function getProject(projectId: string): Promise<any> {
  return service({ url: `/api/graph/project/${projectId}`, method: 'get' })
}
