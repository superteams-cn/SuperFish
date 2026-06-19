/**
 * 把 SuperFish 后端的原始图谱数据（graphiti 风格：节点 uuid/labels/name，
 * 边 source_node_uuid/target_node_uuid/fact/fact_type）在前端转换为 G6 图谱
 * 组件所需的「视图模型」：节点带聚类/颜色/度数/半径，边带谓词/颜色，
 * 并按节点类型聚成簇（供 bubble-sets 背景使用）。
 *
 * kg-gen 原版这层计算在后端（_build_view_model），SuperFish 后端不产出该结构，
 * 故在此前端实现，保持 GraphPanelG6 与现有 d3 版 GraphPanel 接收同一份 GraphData。
 */
import type { GraphData, GraphEdge, GraphNode } from '@/components/GraphPanel'

// 与 d3 版 GraphPanel 一致的实体类型配色，保证两种引擎视觉统一
export const GRAPH_COLORS = [
  '#FF6B35',
  '#004E89',
  '#7B2D8E',
  '#1A936F',
  '#C5283D',
  '#E9724C',
  '#3498db',
  '#9b59b6',
  '#27ae60',
  '#f39c12',
]

export interface GraphViewNode {
  id: string
  label: string
  cluster: string
  color: string
  degree: number
  radius: number
  raw: GraphNode
}

export interface GraphViewEdge {
  id: string
  source: string
  target: string
  /** 源/目标节点的显示名称（节点 id 为 uuid，展示需用名称）。 */
  sourceLabel: string
  targetLabel: string
  predicate: string
  color: string
  raw: GraphEdge
}

export interface GraphViewCluster {
  id: string
  color: string
  members: string[]
}

export interface GraphViewModel {
  nodes: GraphViewNode[]
  edges: GraphViewEdge[]
  clusters: GraphViewCluster[]
  isolatedEntities: string[]
}

/** 取节点 id：后端实际返回 uuid，旧数据可能用 id。 */
function nodeId(n: GraphNode): string {
  return n.uuid ?? n.id ?? ''
}

/** 取节点类型：labels 中第一个非 Entity 的标签。 */
function nodeType(n: GraphNode): string {
  return n.labels?.find((l) => l !== 'Entity') || 'Entity'
}

export function buildGraphView(data: GraphData | null): GraphViewModel {
  const empty: GraphViewModel = { nodes: [], edges: [], clusters: [], isolatedEntities: [] }
  if (!data?.nodes?.length) return empty

  const rawNodes = data.nodes
  const rawEdges = data.edges ?? []

  // 类型 → 颜色
  const typeColor = new Map<string, string>()
  for (const n of rawNodes) {
    const type = nodeType(n)
    if (!typeColor.has(type))
      typeColor.set(type, GRAPH_COLORS[typeColor.size % GRAPH_COLORS.length])
  }

  const idSet = new Set(rawNodes.map(nodeId).filter(Boolean))

  // 度数统计（仅统计两端都存在的有效边，自环计 1 次）
  const degree = new Map<string, number>()
  const validEdges: GraphEdge[] = []
  for (const e of rawEdges) {
    const s = e.source_node_uuid
    const tg = e.target_node_uuid
    if (!idSet.has(s) || !idSet.has(tg)) continue
    validEdges.push(e)
    degree.set(s, (degree.get(s) ?? 0) + 1)
    if (s !== tg) degree.set(tg, (degree.get(tg) ?? 0) + 1)
  }

  const maxDegree = Math.max(1, ...degree.values())

  const nodes: GraphViewNode[] = rawNodes.map((n) => {
    const id = nodeId(n)
    const cluster = nodeType(n)
    const deg = degree.get(id) ?? 0
    // 半径按度数在 [18, 46] 之间线性缩放
    const radius = 18 + Math.round((deg / maxDegree) * 28)
    return {
      id,
      label: n.name || 'Unnamed',
      cluster,
      color: typeColor.get(cluster) || '#999',
      degree: deg,
      radius,
      raw: n,
    }
  })

  // 节点 id → 颜色/名称，供边按源节点着色及端点名称展示（避免逐边线性查找）
  const colorById = new Map(nodes.map((n) => [n.id, n.color]))
  const labelById = new Map(nodes.map((n) => [n.id, n.label]))

  // 边 id：优先用 uuid，否则用 源>谓词>目标#序号 兜底保证唯一
  const seen = new Map<string, number>()
  const edges: GraphViewEdge[] = validEdges.map((e) => {
    const predicate = e.name || e.fact_type || 'RELATED'
    let id = e.uuid
    if (!id) {
      const base = `${e.source_node_uuid}>${predicate}>${e.target_node_uuid}`
      const n = (seen.get(base) ?? 0) + 1
      seen.set(base, n)
      id = `${base}#${n}`
    }
    return {
      id,
      source: e.source_node_uuid,
      target: e.target_node_uuid,
      sourceLabel: e.source_node_name || labelById.get(e.source_node_uuid) || e.source_node_uuid,
      targetLabel: e.target_node_name || labelById.get(e.target_node_uuid) || e.target_node_uuid,
      predicate,
      color: colorById.get(e.source_node_uuid) || '#94a3b8',
      raw: e,
    }
  })

  // 聚类：按节点类型分组（成员为该类型的全部节点 id）
  const clusterMembers = new Map<string, string[]>()
  for (const n of nodes) {
    const arr = clusterMembers.get(n.cluster) ?? []
    arr.push(n.id)
    clusterMembers.set(n.cluster, arr)
  }
  const clusters: GraphViewCluster[] = [...clusterMembers.entries()].map(([id, members]) => ({
    id,
    color: typeColor.get(id) || '#999',
    members,
  }))

  const isolatedEntities = nodes.filter((n) => n.degree === 0).map((n) => n.id)

  return { nodes, edges, clusters, isolatedEntities }
}
