import { useEffect, useMemo, useRef } from 'react'
import * as d3 from 'd3'
import type { TFunction } from 'i18next'

import { nodeType, type GraphData, type GraphEdge, type GraphNode } from '@/lib/graph-types'

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
  bidirectional: boolean
  raw: Record<string, unknown>
}

/** 详情面板选中项（与 GraphPanel 共享）。 */
export type SelectedNode = { kind: 'node'; data: GraphNode; entityType: string; color: string }
export type SelectedEdge = { kind: 'edge'; data: Record<string, unknown> }
export type Selected = SelectedNode | SelectedEdge | null

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

interface Options {
  graphData: GraphData | null
  /** 边标签显隐（受控于面板工具栏）。 */
  showEdgeLabels: boolean
  /** 选中节点/边时回调（面板用于打开详情）。 */
  onSelect: (sel: Selected) => void
  t: TFunction
}

/**
 * 知识图谱 d3 力导向渲染引擎。
 *
 * 把整套命令式 d3 渲染（仿真、缩放/拖拽、曲边/自环、箭头、标签、视图自适配）从面板组件中
 * 抽离，仅暴露 svgRef / containerRef 供挂载，以及 typeColors 供图例复用。行为与原内联实现一致。
 */
export function useForceGraph({ graphData, showEdgeLabels, onSelect, t }: Options) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // 边标签选择集 + 最新开关值（供 d3 闭包读取，避免重建整图）
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
    const directed = new Set<string>() // 有向边集合，用于判定双向关系
    valid.forEach((e) => {
      if (e.source_node_uuid === e.target_node_uuid) {
        ;(selfLoops[e.source_node_uuid] ??= []).push(e)
      } else {
        const key = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
        pairCount[key] = (pairCount[key] || 0) + 1
        directed.add(`${e.source_node_uuid}>${e.target_node_uuid}`)
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
          bidirectional: false,
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
        bidirectional: directed.has(`${e.target_node_uuid}>${e.source_node_uuid}`),
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

    // 箭头标记：常态(灰)/高亮(粉)两色；userSpaceOnUse 固定大小，orient=auto 沿路径朝向
    const defs = svg.append('defs')
    const makeArrow = (id: string, color: string) =>
      defs
        .append('marker')
        .attr('id', id)
        .attr('viewBox', '0 0 10 10')
        .attr('refX', 10)
        .attr('refY', 5)
        .attr('markerUnits', 'userSpaceOnUse')
        .attr('markerWidth', 9)
        .attr('markerHeight', 9)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,0 L10,5 L0,10 z')
        .attr('fill', color)
    makeArrow('sf-arrow', EDGE_COLOR)
    makeArrow('sf-arrow-hl', EDGE_HL)

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
      // 双向关系(A→B 且 B→A)方向相互，不画箭头
      .attr('marker-end', (d) => (d.bidirectional ? null : 'url(#sf-arrow)'))
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation()
        resetHighlight()
        d3.select(event.currentTarget as SVGPathElement)
          .attr('stroke', EDGE_HL)
          .attr('stroke-width', 3)
          .attr('marker-end', d.bidirectional ? null : 'url(#sf-arrow-hl)')
        onSelect({ kind: 'edge', data: d.raw })
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
          .attr('marker-end', d.bidirectional ? null : 'url(#sf-arrow-hl)')
        onSelect({ kind: 'edge', data: d.raw })
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
      link
        .attr('stroke', EDGE_COLOR)
        .attr('stroke-width', 1.4)
        .attr('marker-end', (d) => (d.bidirectional ? null : 'url(#sf-arrow)'))
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
          .attr('marker-end', (l) => (l.bidirectional ? null : 'url(#sf-arrow-hl)'))
        onSelect({ kind: 'node', data: d.raw, entityType: d.type, color: colorOf(d.type) })
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
      onSelect(null)
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
      // 有箭头(单向)时末端回缩到节点边缘，使箭头落在外沿；双向无箭头则画到中心
      const gap = d.bidirectional ? 0 : NODE_R + 5
      if (d.curvature === 0) {
        const dx = tx - sx
        const dy = ty - sy
        const dist = Math.hypot(dx, dy) || 1
        const ex = tx - (dx / dist) * gap
        const ey = ty - (dy / dist) * gap
        return `M${sx},${sy} L${ex},${ey}`
      }
      const dx = tx - sx
      const dy = ty - sy
      const dist = Math.hypot(dx, dy) || 1
      const offset = Math.max(35, dist * (0.25 + d.pairTotal * 0.05))
      const cx = (sx + tx) / 2 + (-dy / dist) * d.curvature * offset
      const cy = (sy + ty) / 2 + (dx / dist) * d.curvature * offset
      // 曲线末端切线方向 ≈ (终点 - 控制点)，沿该方向回缩
      const tgx = tx - cx
      const tgy = ty - cy
      const tgd = Math.hypot(tgx, tgy) || 1
      const ex = tx - (tgx / tgd) * gap
      const ey = ty - (tgy / tgd) * gap
      return `M${sx},${sy} Q${cx},${cy} ${ex},${ey}`
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

  return { svgRef, containerRef, typeColors }
}
