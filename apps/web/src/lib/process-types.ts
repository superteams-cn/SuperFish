import type { GraphData } from '@/components/GraphPanel'

/** 系统日志行 */
export interface SystemLog {
  time: string
  msg: string
}

/** 本体属性 */
export interface OntologyAttr {
  name: string
  type: string
  description?: string
}

/** 本体条目（实体类型 / 关系类型） */
export interface OntologyItem {
  name: string
  description?: string
  attributes?: OntologyAttr[]
  examples?: string[]
  source_targets?: { source: string; target: string }[]
}

/** 项目数据（后端 /api/graph/project 返回，按需取用） */
export interface ProjectData {
  project_id: string
  name?: string
  status?: string
  graph_id?: string | null
  graph_build_task_id?: string | null
  ontology?: {
    entity_types?: OntologyItem[]
    edge_types?: OntologyItem[]
  }
  analysis_summary?: string
  [key: string]: unknown
}

export type { GraphData }

/** 构建进度 */
export interface BuildProgress {
  progress: number
  message?: string
}

/** 本体生成进度 */
export interface OntologyProgress {
  message?: string
}
