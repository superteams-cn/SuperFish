// ===== 图谱数据类型（与后端 /api/graph/data 返回结构一致）=====
// 由 GraphPanel / graph-view 等共享；GraphPanel 仍 re-export 以兼容旧引用路径。

export interface GraphNode {
  // 后端实际返回 uuid，旧数据可能用 id，两者择一
  uuid?: string
  id?: string
  name?: string
  labels?: string[]
  summary?: string
  attributes?: Record<string, unknown>
  created_at?: string | null
  [key: string]: unknown
}

export interface GraphEdge {
  uuid?: string
  source_node_uuid: string
  target_node_uuid: string
  source_node_name?: string
  target_node_name?: string
  fact?: string
  fact_type?: string
  name?: string
  attributes?: Record<string, unknown>
  episodes?: string[]
  created_at?: string | null
  valid_at?: string | null
  [key: string]: unknown
}

export interface GraphData {
  nodes?: GraphNode[]
  edges?: GraphEdge[]
  node_count?: number
  edge_count?: number
}

/** 取节点类型：labels 中第一个非 Entity 的标签。 */
export function nodeType(node: GraphNode): string {
  return node.labels?.find((l) => l !== 'Entity') || 'Entity'
}
