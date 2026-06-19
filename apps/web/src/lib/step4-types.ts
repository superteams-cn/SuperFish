/** 报告生成（Step4）相关数据类型 */

/** 报告大纲 */
export interface ReportOutline {
  title?: string
  summary?: string
  sections?: { title: string }[]
}

/** Agent 执行日志条目（结构化） */
export interface AgentLogEntry {
  action: string // report_start / planning_start / planning_complete / section_start / section_content / section_complete / tool_call / tool_result / llm_response / report_complete
  timestamp?: string
  section_index?: number
  section_title?: string
  elapsed_seconds?: number
  details?: {
    message?: string
    outline?: ReportOutline
    content?: string
    tool_name?: string
    parameters?: Record<string, unknown>
    response?: string
    result?: unknown
    [key: string]: unknown
  }
  [key: string]: unknown
}
