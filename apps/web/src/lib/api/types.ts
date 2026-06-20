/**
 * API 响应类型。
 *
 * 后端统一信封：成功 { success: true, data }，失败由拦截器抛错。
 * axios 响应拦截器已把 response.data 解包，故各接口实际 resolve 为本信封对象。
 */

import type { GraphData, ProjectData } from '@/lib/process-types'
import type { Profile, SimulationConfig } from '@/lib/step2-types'
import type { ActionItem, RunStatus } from '@/lib/step3-types'
import type { AgentLogEntry, ReportOutline } from '@/lib/step4-types'

/**
 * 统一响应信封。
 *
 * 注意：axios 响应拦截器在 `success===false` 或 HTTP 错误时会 reject，
 * 因此 Promise 成功 resolve 时 data 必然存在，故 data 设为必填（而非可选），
 * 避免消费侧到处做 undefined 收窄。失败一律走 catch。
 */
export interface ApiEnvelope<T> {
  success: boolean
  data: T
  error?: string
}

// ===== 任务 =====
export interface TaskData {
  task_id?: string
  status?: string
  progress?: number
  message?: string
  error?: string
  result?: Record<string, unknown>
  progress_detail?: {
    current_stage?: string
    current_stage_name?: string
    stage_index?: number
    total_stages?: number
    current_item?: number
    total_items?: number
    item_description?: string
  }
  [k: string]: unknown
}

// ===== 图谱 =====
export interface BuildGraphResult {
  project_id: string
  task_id: string
  message?: string
}

// ===== 模拟 =====
export interface SimulationData {
  simulation_id?: string
  project_id?: string
  graph_id?: string
  status?: string
  config_generated?: boolean
  entities_count?: number
  [k: string]: unknown
}

export interface PrepareResult {
  task_id?: string
  already_prepared?: boolean
  expected_entities_count?: number
  entity_types?: string[]
  [k: string]: unknown
}

export interface PrepareStatusData extends TaskData {
  already_prepared?: boolean
  report_id?: string
}

export interface ProfilesRealtimeData {
  profiles?: Profile[]
  total_expected?: number
}

export interface ConfigRealtimeData {
  config?: SimulationConfig
  config_generated?: boolean
  generation_stage?: string
  time_config?: SimulationConfig['time_config']
  summary?: {
    total_agents?: number
    simulation_hours?: number
    initial_posts_count?: number
    hot_topics_count?: number
    has_twitter_config?: boolean
    has_reddit_config?: boolean
  }
}

export type StartSimulationData = RunStatus & {
  process_pid?: number
  force_restarted?: boolean
}

export interface RunStatusDetailData {
  all_actions?: ActionItem[]
}

export interface InterviewResult {
  result?: Record<string, { response?: string; answer?: string }>
  results?: Record<string, { response?: string; answer?: string }>
  [k: string]: unknown
}

export interface HistoryProject {
  simulation_id?: string
  project_id?: string
  report_id?: string
  simulation_requirement?: string
  files?: { filename: string }[]
  created_at?: string
  current_round?: number
  total_rounds?: number
}

// ===== 报告 =====
export interface GenerateReportData {
  report_id?: string
  task_id?: string
  simulation_id?: string
  status?: string
  already_generated?: boolean
}

export interface ReportData {
  report_id?: string
  simulation_id?: string
  status?: string
  outline?: ReportOutline
  markdown_content?: string
  [k: string]: unknown
}

export interface ReportProgressData {
  stage?: string
  progress?: number
  message?: string
  current_section?: string | null
  completed_sections?: string[]
  status?: string
  [k: string]: unknown
}

export interface ReportSectionData {
  filename?: string
  section_index?: number
  content?: string
}

export interface ReportSectionsData {
  report_id?: string
  sections?: ReportSectionData[]
  total_sections?: number
  is_complete?: boolean
}

export interface AgentLogData {
  logs?: AgentLogEntry[]
  from_line: number
  total_lines?: number
  has_more?: boolean
}

export interface ConsoleLogData {
  logs?: string[]
  from_line: number
  total_lines?: number
  has_more?: boolean
}

export interface ChatData {
  response?: string
  answer?: string
  [k: string]: unknown
}

export type { GraphData, ProjectData }
