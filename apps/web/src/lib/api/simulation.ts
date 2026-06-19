import service, { requestWithRetry } from './client'

/** 创建模拟。data: { project_id, graph_id?, enable_twitter?, enable_reddit? } */
export const createSimulation = (data: Record<string, unknown>): Promise<any> =>
  requestWithRetry(() => service.post('/api/simulation/create', data), 3, 1000)

/** 准备模拟环境（异步任务）。 */
export const prepareSimulation = (data: Record<string, unknown>): Promise<any> =>
  requestWithRetry(() => service.post('/api/simulation/prepare', data), 3, 1000)

/** 查询准备任务进度。data: { task_id?, simulation_id? } */
export const getPrepareStatus = (data: Record<string, unknown>): Promise<any> =>
  service.post('/api/simulation/prepare/status', data)

/** 获取模拟状态。 */
export const getSimulation = (simulationId: string): Promise<any> =>
  service.get(`/api/simulation/${simulationId}`)

/** 获取模拟的 Agent Profiles。 */
export const getSimulationProfiles = (simulationId: string, platform = 'reddit'): Promise<any> =>
  service.get(`/api/simulation/${simulationId}/profiles`, { params: { platform } })

/** 实时获取生成中的 Agent Profiles。 */
export const getSimulationProfilesRealtime = (
  simulationId: string,
  platform = 'reddit',
): Promise<any> =>
  service.get(`/api/simulation/${simulationId}/profiles/realtime`, { params: { platform } })

/** 获取模拟配置。 */
export const getSimulationConfig = (simulationId: string): Promise<any> =>
  service.get(`/api/simulation/${simulationId}/config`)

/** 实时获取生成中的模拟配置。 */
export const getSimulationConfigRealtime = (simulationId: string): Promise<any> =>
  service.get(`/api/simulation/${simulationId}/config/realtime`)

/** 列出所有模拟，可按项目ID过滤。 */
export const listSimulations = (projectId?: string): Promise<any> => {
  const params = projectId ? { project_id: projectId } : {}
  return service.get('/api/simulation/list', { params })
}

/** 启动模拟。 */
export const startSimulation = (data: Record<string, unknown>): Promise<any> =>
  requestWithRetry(() => service.post('/api/simulation/start', data), 3, 1000)

/** 停止模拟。 */
export const stopSimulation = (data: Record<string, unknown>): Promise<any> =>
  service.post('/api/simulation/stop', data)

/** 获取模拟运行实时状态。 */
export const getRunStatus = (simulationId: string): Promise<any> =>
  service.get(`/api/simulation/${simulationId}/run-status`)

/** 获取模拟运行详细状态（含最近动作）。 */
export const getRunStatusDetail = (simulationId: string): Promise<any> =>
  service.get(`/api/simulation/${simulationId}/run-status/detail`)

/** 获取模拟中的帖子。 */
export const getSimulationPosts = (
  simulationId: string,
  platform = 'reddit',
  limit = 50,
  offset = 0,
): Promise<any> =>
  service.get(`/api/simulation/${simulationId}/posts`, { params: { platform, limit, offset } })

/** 获取模拟时间线（按轮次汇总）。 */
export const getSimulationTimeline = (
  simulationId: string,
  startRound = 0,
  endRound: number | null = null,
): Promise<any> => {
  const params: Record<string, number> = { start_round: startRound }
  if (endRound !== null) params.end_round = endRound
  return service.get(`/api/simulation/${simulationId}/timeline`, { params })
}

/** 获取 Agent 统计信息。 */
export const getAgentStats = (simulationId: string): Promise<any> =>
  service.get(`/api/simulation/${simulationId}/agent-stats`)

/** 获取模拟动作历史。 */
export const getSimulationActions = (
  simulationId: string,
  params: Record<string, unknown> = {},
): Promise<any> => service.get(`/api/simulation/${simulationId}/actions`, { params })

/** 关闭模拟环境（优雅退出）。 */
export const closeSimulationEnv = (data: Record<string, unknown>): Promise<any> =>
  service.post('/api/simulation/close-env', data)

/** 获取模拟环境状态。 */
export const getEnvStatus = (data: Record<string, unknown>): Promise<any> =>
  service.post('/api/simulation/env-status', data)

/** 批量采访 Agent。 */
export const interviewAgents = (data: Record<string, unknown>): Promise<any> =>
  requestWithRetry(() => service.post('/api/simulation/interview/batch', data), 3, 1000)

/** 获取历史模拟列表（带项目详情），用于首页历史项目展示。 */
export const getSimulationHistory = (limit = 20): Promise<any> =>
  service.get('/api/simulation/history', { params: { limit } })
