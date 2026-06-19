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
    result_length?: number
    [key: string]: unknown
  }
  [key: string]: unknown
}

/* ── 工具结果结构化解析类型 ────────────────────────────────── */

/** 知识图谱关系链（A --[rel]--> B） */
export interface RelationLink {
  source: string
  relation: string
  target: string
}

/** 命名实体（带可选类型/摘要/关联事实数） */
export interface NamedEntity {
  name: string
  type?: string
  summary?: string
  relatedFactsCount?: number
}

/** insight_forge（深度洞察）解析结果 */
export interface InsightResult {
  query: string
  simulationRequirement: string
  stats: { facts: number; entities: number; relationships: number }
  subQueries: string[]
  facts: string[]
  entities: NamedEntity[]
  relations: RelationLink[]
}

/** panorama_search（全景搜索）解析结果 */
export interface PanoramaResult {
  query: string
  stats: { nodes: number; edges: number; activeFacts: number; historicalFacts: number }
  activeFacts: string[]
  historicalFacts: string[]
  entities: NamedEntity[]
}

/** 单条采访记录 */
export interface InterviewRecord {
  num: number
  title: string
  name: string
  role: string
  bio: string
  selectionReason: string
  questions: string[]
  twitterAnswer: string
  redditAnswer: string
  quotes: string[]
}

/** interview_agents（Agent 采访）解析结果 */
export interface InterviewResult {
  topic: string
  successCount: number
  totalCount: number
  selectionReason: string
  interviews: InterviewRecord[]
  summary: string
}

/** quick_search（快速搜索）解析结果 */
export interface QuickSearchResult {
  query: string
  count: number
  facts: string[]
  edges: RelationLink[]
  nodes: NamedEntity[]
}
