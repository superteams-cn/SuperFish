import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import * as d3 from 'd3'
import { RefreshCw, Maximize2, X, Network, Tag, ChevronDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/common/EmptyState'
import { cn } from '@/lib/utils'

// ===== 图谱数据类型（与后端 /api/graph/data 返回结构一致）=====
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

interface GraphPanelProps {
  graphData: GraphData | null
  loading?: boolean
  /** 当前流程阶段：1 表示图谱构建中，用于显示“实时更新中”提示 */
  currentPhase?: number
  /** 是否正在模拟，用于显示“记忆实时更新”提示 */
  isSimulating?: boolean
  onRefresh?: () => void
  onToggleMaximize?: () => void
}

// d3 仿真用的内部节点/连线类型
interface SimNode extends d3.SimulationNodeDatum {
  id: string
  name: string
  type: string
  raw: GraphNode
}
interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  type: string
  name: string
  curvature: number
  isSelfLoop: boolean
  pairTotal: number
  raw: Record<string, unknown>
}

// 详情面板选中项
type SelectedNode = { kind: 'node'; data: GraphNode; entityType: string; color: string }
type SelectedEdge = { kind: 'edge'; data: Record<string, unknown> }
type Selected = SelectedNode | SelectedEdge | null

// 取节点类型：labels 中第一个非 Entity 的标签
function nodeType(node: GraphNode): string {
  return node.labels?.find((l) => l !== 'Entity') || 'Entity'
}

const COLORS = [
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

const EDGE_COLOR = '#cbd5e1'
const EDGE_HL = '#E91E63'
const NODE_HL = '#E91E63'

function str(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return dateStr
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** 知识图谱可视化面板（d3 力导向图）。 */
export function GraphPanel({
  graphData,
  loading,
  currentPhase,
  isSimulating,
  onRefresh,
  onToggleMaximize,
}: GraphPanelProps) {
  const { t } = useTranslation()
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<Selected>(null)
  const [expandedLoops, setExpandedLoops] = useState<Set<string>>(new Set())

  const nodeCount = graphData?.nodes?.length ?? 0
  const edgeCount = graphData?.edges?.length ?? 0
  // 大图默认关闭边标签，避免标签过密拖慢渲染
  const [showEdgeLabels, setShowEdgeLabels] = useState(true)

  // 边标签开关的最新值（供 d3 闭包读取，避免重建整图）
  const edgeLabelSelRef = useRef<d3.Selection<
    SVGTextElement,
    SimLink,
    SVGGElement,
    unknown
  > | null>(null)
  const showEdgeLabelsRef = useRef(showEdgeLabels)
  showEdgeLabelsRef.current = showEdgeLabels
  // 切换标签为显示时刷新一次位置（仿真可能已停止，tick 不再触发）
  const refreshEdgeLabelsRef = useRef<(() => void) | null>(null)
  // 将图谱缩放平移到适配当前容器（视图切换/容器尺寸变化时调用）
  const fitViewRef = useRef<((duration?: number) => void) | null>(null)

  // 实体类型 → 颜色映射，供图例与节点着色复用
  const typeColors = useMemo(() => {
    const map = new Map<string, string>()
    graphData?.nodes?.forEach((n) => {
      const type = nodeType(n)
      if (!map.has(type)) map.set(type, COLORS[map.size % COLORS.length])
    })
    return map
  }, [graphData])

  // 切到大图时自动关闭边标签
  useEffect(() => {
    setShowEdgeLabels(edgeCount <= 80)
  }, [edgeCount, graphData])

  // 选中项变化时收起所有自环展开项
  useEffect(() => {
    setExpandedLoops(new Set())
  }, [selected])

  useEffect(() => {
    if (!svgRef.current || !containerRef.current) return
    const nodesData = graphData?.nodes ?? []
    const edgesData = graphData?.edges ?? []

    const width = containerRef.current.clientWidth
    const height = containerRef.current.clientHeight

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    edgeLabelSelRef.current = null
    if (nodesData.length === 0) return

    const colorOf = (type: string) => typeColors.get(type) || '#999'

    // ---- 节点 ----
    const nodes: SimNode[] = nodesData.map((n) => ({
      id: n.uuid ?? n.id ?? '',
      name: n.name || 'Unnamed',
      type: nodeType(n),
      raw: n,
    }))
    const nodeMap = new Map(nodesData.map((n) => [n.uuid ?? n.id ?? '', n]))
    const nodeIds = new Set(nodes.map((n) => n.id))

    // ---- 边：分离自环、统计多重边、计算曲率 ----
    const valid = edgesData.filter(
      (e) => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid),
    )

    const pairCount: Record<string, number> = {}
    const selfLoops: Record<string, GraphEdge[]> = {}
    valid.forEach((e) => {
      if (e.source_node_uuid === e.target_node_uuid) {
        ;(selfLoops[e.source_node_uuid] ??= []).push(e)
      } else {
        const key = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
        pairCount[key] = (pairCount[key] || 0) + 1
      }
    })

    const pairIndex: Record<string, number> = {}
    const seenSelfLoop = new Set<string>()
    const links: SimLink[] = []

    valid.forEach((e) => {
      if (e.source_node_uuid === e.target_node_uuid) {
        if (seenSelfLoop.has(e.source_node_uuid)) return
        seenSelfLoop.add(e.source_node_uuid)
        const group = selfLoops[e.source_node_uuid]
        const name = nodeMap.get(e.source_node_uuid)?.name || 'Unknown'
        links.push({
          source: e.source_node_uuid,
          target: e.target_node_uuid,
          type: 'SELF_LOOP',
          name: `${t('graph.selfRelations')} (${group.length})`,
          curvature: 0,
          isSelfLoop: true,
          pairTotal: 1,
          raw: {
            isSelfLoopGroup: true,
            source_name: name,
            selfLoopCount: group.length,
            selfLoopEdges: group,
          },
        })
        return
      }

      const key = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
      const total = pairCount[key]
      const idx = pairIndex[key] || 0
      pairIndex[key] = idx + 1
      const reversed = e.source_node_uuid > e.target_node_uuid
      let curvature = 0
      if (total > 1) {
        const range = Math.min(1.2, 0.6 + total * 0.15)
        curvature = (idx / (total - 1) - 0.5) * range * 2
        if (reversed) curvature = -curvature
      }
      links.push({
        source: e.source_node_uuid,
        target: e.target_node_uuid,
        type: e.fact_type || e.name || 'RELATED',
        name: e.name || e.fact_type || 'RELATED',
        curvature,
        isSelfLoop: false,
        pairTotal: total,
        raw: {
          ...e,
          source_name: e.source_node_name || nodeMap.get(e.source_node_uuid)?.name,
          target_name: e.target_node_name || nodeMap.get(e.target_node_uuid)?.name,
        },
      })
    })

    // ---- 规模自适应参数 ----
    const count = nodes.length
    const isLarge = count > 200
    const isHuge = count > 500
    const NODE_R = isHuge ? 6 : count > 150 ? 9 : 12
    const showNodeLabelsByCount = count <= 120

    const root = svg.append('g')

    // 缩放/平移：放缓滚轮步进；禁用双击缩放（与拖拽冲突）
    let labelsVisible = showNodeLabelsByCount
    const applyNodeLabelVisibility = (k: number) => {
      const next = showNodeLabelsByCount || k > 1.4
      if (next !== labelsVisible) {
        labelsVisible = next
        nodeLabel.style('display', next ? 'block' : 'none')
      }
    }
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .wheelDelta((event) => -event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.0015))
      .on('zoom', (event) => {
        root.attr('transform', event.transform)
        applyNodeLabelVisibility(event.transform.k)
      })
    svg.call(zoom).on('dblclick.zoom', null)

    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance((d) => 90 + ((d.pairTotal || 1) - 1) * 45),
      )
      .force(
        'charge',
        d3
          .forceManyBody<SimNode>()
          .strength(isLarge ? -180 : -320)
          .distanceMax(isLarge ? 500 : Infinity),
      )
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide<SimNode>(NODE_R + 6))
      .force('x', d3.forceX(width / 2).strength(0.04))
      .force('y', d3.forceY(height / 2).strength(0.04))
      .velocityDecay(0.4)
      .alphaDecay(isLarge ? 0.05 : 0.0228)

    // ---- 边（path 支持曲线/自环）----
    const linkGroup = root.append('g')
    const link = linkGroup
      .selectAll<SVGPathElement, SimLink>('path')
      .data(links)
      .join('path')
      .attr('fill', 'none')
      .attr('stroke', EDGE_COLOR)
      .attr('stroke-opacity', 0.75)
      .attr('stroke-width', 1.4)
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation()
        resetHighlight()
        d3.select(event.currentTarget as SVGPathElement)
          .attr('stroke', EDGE_HL)
          .attr('stroke-width', 3)
        setSelected({ kind: 'edge', data: d.raw })
      })

    // 边标签：用 paint-order 描边做白色光晕，省去逐 tick getBBox（大图关键优化）
    const edgeLabel = linkGroup
      .selectAll<SVGTextElement, SimLink>('text')
      .data(links)
      .join('text')
      .text((d) => d.name)
      .attr('font-size', 9)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', '#555')
      .attr('stroke', 'rgba(255,255,255,0.95)')
      .attr('stroke-width', 3)
      .attr('stroke-linejoin', 'round')
      .attr('paint-order', 'stroke')
      .style('cursor', 'pointer')
      .style('display', showEdgeLabels ? 'block' : 'none')
      .style('font-family', 'system-ui, sans-serif')
      .on('click', (event, d) => {
        event.stopPropagation()
        resetHighlight()
        link
          .filter((l) => l === d)
          .attr('stroke', EDGE_HL)
          .attr('stroke-width', 3)
        setSelected({ kind: 'edge', data: d.raw })
      })
    edgeLabelSelRef.current = edgeLabel

    // ---- 节点（g：圆 + 标签，单次 transform 写入）----
    const nodeG = root
      .append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .style('cursor', 'pointer')

    const circle = nodeG
      .append('circle')
      .attr('r', NODE_R)
      .attr('fill', (d) => colorOf(d.type))
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)

    const nodeLabel = nodeG
      .append('text')
      .text((d) => (d.name.length > 12 ? `${d.name.slice(0, 12)}…` : d.name))
      .attr('x', NODE_R + 4)
      .attr('y', 4)
      .attr('font-size', 11)
      .attr('font-weight', 500)
      .attr('fill', 'currentColor')
      .attr('stroke', 'var(--background, #fff)')
      .attr('stroke-width', 3)
      .attr('paint-order', 'stroke')
      .style('pointer-events', 'none')
      .style('font-family', 'system-ui, sans-serif')
      .style('display', labelsVisible ? 'block' : 'none')

    function resetHighlight() {
      link.attr('stroke', EDGE_COLOR).attr('stroke-width', 1.4)
      circle.attr('stroke', '#fff').attr('stroke-width', 2)
    }

    nodeG
      .on('click', (event, d) => {
        event.stopPropagation()
        resetHighlight()
        d3.select(event.currentTarget as SVGGElement)
          .select('circle')
          .attr('stroke', NODE_HL)
          .attr('stroke-width', 4)
        link
          .filter((l) => (l.source as SimNode).id === d.id || (l.target as SimNode).id === d.id)
          .attr('stroke', EDGE_HL)
          .attr('stroke-width', 2.4)
        setSelected({ kind: 'node', data: d.raw, entityType: d.type, color: colorOf(d.type) })
      })
      .on('mouseenter', (event) => {
        const c = d3.select(event.currentTarget as SVGGElement).select<SVGCircleElement>('circle')
        if (c.attr('stroke') !== NODE_HL) c.attr('stroke', '#334155').attr('stroke-width', 3)
      })
      .on('mouseleave', (event) => {
        const c = d3.select(event.currentTarget as SVGGElement).select<SVGCircleElement>('circle')
        if (c.attr('stroke') !== NODE_HL) c.attr('stroke', '#fff').attr('stroke-width', 2)
      })
      .call(
        d3
          .drag<SVGGElement, SimNode>()
          .on('start', (event, d) => {
            d.fx = d.x
            d.fy = d.y
            ;(d as { _sx?: number })._sx = event.x
            ;(d as { _sy?: number })._sy = event.y
            ;(d as { _dragging?: boolean })._dragging = false
          })
          .on('drag', (event, d) => {
            const dd = d as { _sx?: number; _sy?: number; _dragging?: boolean }
            const dist = Math.hypot(event.x - (dd._sx ?? 0), event.y - (dd._sy ?? 0))
            if (!dd._dragging && dist > 3) {
              dd._dragging = true
              if (!event.active) simulation.alphaTarget(0.3).restart()
            }
            if (dd._dragging) {
              d.fx = event.x
              d.fy = event.y
            }
          })
          .on('end', (event, d) => {
            const dd = d as { _dragging?: boolean }
            if (dd._dragging && !event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
            dd._dragging = false
          }),
      )

    // 点击空白取消选中
    svg.on('click', () => {
      resetHighlight()
      setSelected(null)
    })

    // ---- 路径计算 ----
    const linkPath = (d: SimLink) => {
      const s = d.source as SimNode
      const tg = d.target as SimNode
      const sx = s.x ?? 0
      const sy = s.y ?? 0
      const tx = tg.x ?? 0
      const ty = tg.y ?? 0
      if (d.isSelfLoop) {
        const r = NODE_R + 18
        return `M${sx + NODE_R * 0.6},${sy - 4} A${r},${r} 0 1,1 ${sx + NODE_R * 0.6},${sy + 4}`
      }
      if (d.curvature === 0) return `M${sx},${sy} L${tx},${ty}`
      const dx = tx - sx
      const dy = ty - sy
      const dist = Math.hypot(dx, dy) || 1
      const offset = Math.max(35, dist * (0.25 + d.pairTotal * 0.05))
      const cx = (sx + tx) / 2 + (-dy / dist) * d.curvature * offset
      const cy = (sy + ty) / 2 + (dx / dist) * d.curvature * offset
      return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
    }
    const labelPos = (d: SimLink) => {
      const s = d.source as SimNode
      const tg = d.target as SimNode
      const sx = s.x ?? 0
      const sy = s.y ?? 0
      const tx = tg.x ?? 0
      const ty = tg.y ?? 0
      if (d.isSelfLoop) return { x: sx, y: sy - (NODE_R + 40) }
      if (d.curvature === 0) return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
      const dx = tx - sx
      const dy = ty - sy
      const dist = Math.hypot(dx, dy) || 1
      const offset = Math.max(35, dist * (0.25 + d.pairTotal * 0.05))
      const cx = (sx + tx) / 2 + (-dy / dist) * d.curvature * offset
      const cy = (sy + ty) / 2 + (dx / dist) * d.curvature * offset
      return { x: 0.25 * sx + 0.5 * cx + 0.25 * tx, y: 0.25 * sy + 0.5 * cy + 0.25 * ty }
    }

    const updateEdgeLabelPos = () =>
      edgeLabel.attr('x', (d) => labelPos(d).x).attr('y', (d) => labelPos(d).y)
    refreshEdgeLabelsRef.current = updateEdgeLabelPos

    const ticked = () => {
      link.attr('d', linkPath)
      nodeG.attr('transform', (d) => `translate(${d.x},${d.y})`)
      if (showEdgeLabelsRef.current) updateEdgeLabelPos()
    }
    simulation.on('tick', ticked)

    // 适配视图：按节点包围盒缩放平移，使图谱居中铺满当前容器
    const fitView = (duration = 400) => {
      if (!nodes.length) return
      let minX = Infinity
      let maxX = -Infinity
      let minY = Infinity
      let maxY = -Infinity
      for (const n of nodes) {
        const x = n.x ?? 0
        const y = n.y ?? 0
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
      }
      const w = containerRef.current?.clientWidth || width
      const h = containerRef.current?.clientHeight || height
      if (w <= 0 || h <= 0) return
      const pad = 80
      const bw = Math.max(maxX - minX, 1)
      const bh = Math.max(maxY - minY, 1)
      const scale = Math.min(2, Math.max(0.1, Math.min((w - pad) / bw, (h - pad) / bh)))
      const cx = (minX + maxX) / 2
      const cy = (minY + maxY) / 2
      const transform = d3.zoomIdentity
        .translate(w / 2 - scale * cx, h / 2 - scale * cy)
        .scale(scale)
      svg.transition().duration(duration).call(zoom.transform, transform)
    }
    fitViewRef.current = fitView
    // 仅首次布局收敛后自动适配一次（首屏框图）；拖拽节点引起的再次收敛不重新适配
    let fitted = false
    simulation.on('end', () => {
      if (fitted) return
      fitted = true
      fitView(400)
    })

    // 大图：先预热布局再渲染，避免开局抖动
    if (isLarge) {
      const warm = isHuge ? 120 : 60
      simulation.alpha(1)
      for (let i = 0; i < warm; i++) simulation.tick()
      simulation.alpha(0.3).restart()
    }

    return () => {
      simulation.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, typeColors, t])

  // 边标签开关：仅切换显隐，无需重建整图
  useEffect(() => {
    const sel = edgeLabelSelRef.current
    if (!sel) return
    sel.style('display', showEdgeLabels ? 'block' : 'none')
    if (showEdgeLabels) refreshEdgeLabelsRef.current?.()
  }, [showEdgeLabels])

  // 容器尺寸变化（切换 图谱/双栏/工作台 视图）后自动适配图谱视图
  useEffect(() => {
    const el = containerRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let timer: ReturnType<typeof setTimeout> | null = null
    let first = true
    const ro = new ResizeObserver(() => {
      if (first) {
        first = false // 跳过初次挂载触发
        return
      }
      if (timer) clearTimeout(timer)
      // 等宽度过渡(~300ms)结束后再 fit，避免过程中反复抖动
      timer = setTimeout(() => fitViewRef.current?.(400), 360)
    })
    ro.observe(el)
    return () => {
      if (timer) clearTimeout(timer)
      ro.disconnect()
    }
  }, [])

  const hasData = nodeCount > 0
  const hint =
    currentPhase === 1
      ? t('graph.realtimeUpdating')
      : isSimulating
        ? t('graph.graphMemoryRealtime')
        : null

  const toggleLoop = (id: string) =>
    setExpandedLoops((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div
      ref={containerRef}
      className="bg-muted/30 relative h-full w-full overflow-hidden"
      style={{
        backgroundImage: 'radial-gradient(var(--border) 1px, transparent 1px)',
        backgroundSize: '24px 24px',
      }}
    >
      {/* 工具栏 */}
      <div className="absolute right-3 top-3 z-20 flex gap-2">
        <Button
          variant={showEdgeLabels ? 'default' : 'outline'}
          size="icon"
          onClick={() => setShowEdgeLabels((v) => !v)}
          title={t('graph.showEdgeLabels')}
          className={showEdgeLabels ? '' : 'bg-background'}
        >
          <Tag className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          onClick={onRefresh}
          disabled={loading}
          title={t('graph.refreshGraph')}
          className="bg-background"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
        <Button
          variant="outline"
          size="icon"
          onClick={onToggleMaximize}
          title={t('graph.toggleMaximize')}
          className="bg-background"
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
      </div>

      {/* 图例（左下，含计数） */}
      {hasData && typeColors.size > 0 && (
        <div className="bg-background/90 absolute bottom-3 left-3 z-10 max-w-[320px] rounded-md border p-2.5 text-xs shadow-sm backdrop-blur">
          <div className="text-muted-foreground mb-1.5 font-semibold uppercase tracking-wide">
            {t('graph.entityTypes')}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {Array.from(typeColors.entries()).map(([type, color]) => (
              <div key={type} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                <span className="truncate">{type}</span>
              </div>
            ))}
          </div>
          <div className="text-muted-foreground mt-1.5 border-t pt-1.5">
            {nodeCount} nodes · {edgeCount} edges
          </div>
        </div>
      )}

      <svg ref={svgRef} className="text-foreground h-full w-full" />

      {/* 实时更新提示 */}
      {hasData && hint && (
        <div className="bg-foreground/75 text-background absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full px-4 py-2 text-xs font-medium shadow-lg backdrop-blur">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
          {hint}
        </div>
      )}

      {/* 空状态 */}
      {!hasData && !loading && (
        <div className="absolute inset-0">
          <EmptyState
            icon={Network}
            title={t('graph.noData')}
            description={t('graph.noDataDesc')}
          />
        </div>
      )}

      {/* 详情面板 */}
      {selected && (
        <div className="bg-background absolute right-3 top-16 z-20 flex max-h-[calc(100%-5rem)] w-80 flex-col rounded-lg border shadow-xl">
          <div className="bg-muted/40 flex items-center justify-between gap-2 border-b px-4 py-3">
            <span className="text-sm font-semibold">
              {selected.kind === 'node' ? t('graph.nodeDetails') : t('graph.relationship')}
            </span>
            <div className="flex items-center gap-2">
              {selected.kind === 'node' && (
                <span
                  className="rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
                  style={{ backgroundColor: selected.color }}
                >
                  {selected.entityType}
                </span>
              )}
              <button
                onClick={() => setSelected(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 text-sm">
            {selected.kind === 'node' ? (
              <NodeDetail data={selected.data} t={t} />
            ) : (
              <EdgeDetail
                data={selected.data}
                expanded={expandedLoops}
                onToggle={toggleLoop}
                t={t}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ===== 详情子组件 =====
type TFn = ReturnType<typeof useTranslation>['t']

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  if (!value) return null
  return (
    <div className="mb-2.5 flex flex-wrap gap-x-2">
      <span className="text-muted-foreground min-w-[72px] text-xs font-medium">{label}:</span>
      <span className={cn('flex-1 break-words', mono && 'font-mono text-xs')}>{value}</span>
    </div>
  )
}

function NodeDetail({ data, t }: { data: GraphNode; t: TFn }) {
  const attrs = (data.attributes ?? {}) as Record<string, unknown>
  const attrEntries = Object.entries(attrs).filter(([k]) => k !== 'summary')
  const labels = data.labels ?? []
  return (
    <div>
      <Row label={t('graph.fieldName')} value={str(data.name)} />
      <Row label="UUID" value={str(data.uuid ?? data.id)} mono />
      <Row label={t('graph.fieldCreated')} value={formatDateTime(data.created_at)} />

      {attrEntries.length > 0 && (
        <div className="mt-4 border-t pt-3">
          <div className="text-muted-foreground mb-2 text-xs font-semibold">
            {t('graph.fieldProperties')}
          </div>
          <div className="flex flex-col gap-2">
            {attrEntries.map(([k, v]) => (
              <div key={k} className="flex gap-2 text-xs">
                <span className="text-muted-foreground min-w-[88px] font-medium">{k}:</span>
                <span className="flex-1 break-words">{str(v) || 'None'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.summary && (
        <div className="mt-4 border-t pt-3">
          <div className="text-muted-foreground mb-2 text-xs font-semibold">
            {t('graph.fieldSummary')}
          </div>
          <p className="text-muted-foreground text-xs leading-relaxed">{str(data.summary)}</p>
        </div>
      )}

      {labels.length > 0 && (
        <div className="mt-4 border-t pt-3">
          <div className="text-muted-foreground mb-2 text-xs font-semibold">
            {t('graph.fieldLabels')}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {labels.map((l) => (
              <span key={l} className="bg-muted rounded-full border px-2.5 py-0.5 text-[11px]">
                {l}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function EdgeDetail({
  data,
  expanded,
  onToggle,
  t,
}: {
  data: Record<string, unknown>
  expanded: Set<string>
  onToggle: (id: string) => void
  t: TFn
}) {
  // 自环组
  if (data.isSelfLoopGroup) {
    const loops = (data.selfLoopEdges as GraphEdge[]) ?? []
    return (
      <div>
        <div className="mb-3 flex items-center gap-2 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm font-medium">
          {str(data.source_name)} · {t('graph.selfRelations')}
          <span className="bg-background text-muted-foreground ml-auto rounded-full px-2 py-0.5 text-xs">
            {str(data.selfLoopCount)} {t('common.items')}
          </span>
        </div>
        <div className="flex flex-col gap-2">
          {loops.map((loop, idx) => {
            const id = loop.uuid || String(idx)
            const open = expanded.has(id)
            return (
              <div key={id} className="bg-muted/40 overflow-hidden rounded-md border">
                <button
                  onClick={() => onToggle(id)}
                  className="hover:bg-muted flex w-full items-center gap-2 px-3 py-2 text-left"
                >
                  <span className="text-muted-foreground bg-background rounded px-1.5 py-0.5 text-[10px] font-semibold">
                    #{idx + 1}
                  </span>
                  <span className="flex-1 truncate text-xs font-medium">
                    {loop.name || loop.fact_type || 'RELATED'}
                  </span>
                  <ChevronDown
                    className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')}
                  />
                </button>
                {open && (
                  <div className="border-t px-3 py-2">
                    <Row label="UUID" value={str(loop.uuid)} mono />
                    <Row label={t('graph.fieldFact')} value={str(loop.fact)} />
                    <Row label={t('graph.fieldType')} value={str(loop.fact_type)} />
                    <Row label={t('graph.fieldCreated')} value={formatDateTime(loop.created_at)} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // 普通边
  const episodes = (data.episodes as string[]) ?? []
  return (
    <div>
      <div className="bg-muted/50 mb-3 rounded-md px-3 py-2 text-sm font-medium leading-relaxed">
        {str(data.source_name)} → {str(data.name) || 'RELATED_TO'} → {str(data.target_name)}
      </div>
      <Row label="UUID" value={str(data.uuid)} mono />
      <Row label={t('graph.fieldLabel')} value={str(data.name) || 'RELATED_TO'} />
      <Row label={t('graph.fieldType')} value={str(data.fact_type) || 'Unknown'} />
      <Row label={t('graph.fieldFact')} value={str(data.fact)} />
      <Row label={t('graph.fieldCreated')} value={formatDateTime(str(data.created_at))} />
      <Row label={t('graph.fieldValidFrom')} value={formatDateTime(str(data.valid_at))} />

      {episodes.length > 0 && (
        <div className="mt-4 border-t pt-3">
          <div className="text-muted-foreground mb-2 text-xs font-semibold">
            {t('graph.fieldEpisodes')}
          </div>
          <div className="flex flex-col gap-1.5">
            {episodes.map((ep) => (
              <span key={ep} className="bg-muted rounded border px-2 py-1 font-mono text-[10px]">
                {ep}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
