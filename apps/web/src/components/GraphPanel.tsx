import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import * as d3 from 'd3'
import { RefreshCw, Maximize2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'

// ===== 图谱数据类型（与后端 /api/graph/data 返回结构一致）=====
export interface GraphNode {
  id: string
  name?: string
  labels?: string[]
  [key: string]: unknown
}
export interface GraphEdge {
  source_node_uuid: string
  target_node_uuid: string
  fact_type?: string
  name?: string
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
  onRefresh?: () => void
  onToggleMaximize?: () => void
}

// d3 仿真用的内部节点/连线类型
interface SimNode extends d3.SimulationNodeDatum {
  id: string
  name: string
  type: string
}
interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  type: string
}

// 取节点类型：labels 中第一个非 Entity 的标签
function nodeType(node: GraphNode): string {
  return node.labels?.find((l) => l !== 'Entity') || 'Entity'
}

const COLORS = [
  '#FF5722', '#2196F3', '#4CAF50', '#9C27B0', '#FF9800',
  '#00BCD4', '#E91E63', '#3F51B5', '#8BC34A', '#795548',
]

/** 知识图谱可视化面板（d3 力导向图）。 */
export function GraphPanel({ graphData, loading, onRefresh, onToggleMaximize }: GraphPanelProps) {
  const { t } = useTranslation()
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<SimNode | null>(null)

  // 实体类型 → 颜色映射，供图例与节点着色复用
  const typeColors = useMemo(() => {
    const types = new Set<string>()
    graphData?.nodes?.forEach((n) => types.add(nodeType(n)))
    const map = new Map<string, string>()
    Array.from(types).forEach((type, i) => map.set(type, COLORS[i % COLORS.length]))
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
    if (nodesData.length === 0) return

    const nodes: SimNode[] = nodesData.map((n) => ({
      id: n.id,
      name: n.name || 'Unnamed',
      type: nodeType(n),
    }))
    const nodeIds = new Set(nodes.map((n) => n.id))
    const links: SimLink[] = edgesData
      .filter(
        (e) => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid),
      )
      .map((e) => ({
        source: e.source_node_uuid,
        target: e.target_node_uuid,
        type: e.fact_type || e.name || 'RELATED',
      }))

    const root = svg.append('g')

    // 缩放/平移
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => root.attr('transform', event.transform))
    svg.call(zoom)

    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        'link',
        d3.forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(120),
      )
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide(30))

    const link = root
      .append('g')
      .attr('stroke', '#cbd5e1')
      .attr('stroke-opacity', 0.7)
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke-width', 1.2)

    const node = root
      .append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .style('cursor', 'pointer')
      .on('click', (_event, d) => setSelected(d))
      .call(
        d3
          .drag<SVGGElement, SimNode>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          }),
      )

    node
      .append('circle')
      .attr('r', 14)
      .attr('fill', (d) => typeColors.get(d.type) || '#999')
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)

    node
      .append('text')
      .text((d) => d.name)
      .attr('x', 18)
      .attr('y', 4)
      .attr('font-size', 11)
      .attr('fill', 'currentColor')

    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as SimNode).x!)
        .attr('y1', (d) => (d.source as SimNode).y!)
        .attr('x2', (d) => (d.target as SimNode).x!)
        .attr('y2', (d) => (d.target as SimNode).y!)
      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

    return () => {
      simulation.stop()
    }
  }, [graphData, typeColors])

  const hasData = (graphData?.nodes?.length ?? 0) > 0

  return (
    <div ref={containerRef} className="relative h-full w-full bg-muted/30">
      {/* 工具栏 */}
      <div className="absolute right-3 top-3 z-10 flex gap-2">
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

      {/* 图例 */}
      {hasData && typeColors.size > 0 && (
        <div className="absolute left-3 top-3 z-10 max-w-[200px] rounded-md border bg-background/90 p-2 text-xs shadow-sm">
          {Array.from(typeColors.entries()).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2 py-0.5">
              <span className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
              <span className="truncate">{type}</span>
            </div>
          ))}
        </div>
      )}

      <svg ref={svgRef} className="h-full w-full text-foreground" />

      {/* 空状态 */}
      {!hasData && !loading && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
          {t('graph.noData', { defaultValue: '暂无图谱数据' })}
        </div>
      )}

      {/* 节点详情 */}
      {selected && (
        <div className="absolute bottom-3 left-3 z-10 w-64 rounded-md border bg-background p-3 shadow-md">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">{selected.name}</span>
            <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: typeColors.get(selected.type) || '#999' }}
            />
            {selected.type}
          </div>
        </div>
      )}
    </div>
  )
}
