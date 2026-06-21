import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw, Maximize2, X, Network, Tag, Info } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/common/EmptyState'
import { GraphLegend, GraphRealtimeHint } from '@/components/graph/GraphOverlays'
import { GraphDetailShell } from '@/components/graph/GraphDetailShell'
import { NodeDetail, EdgeDetail } from '@/components/graph/GraphDetailContent'
import { useForceGraph, type Selected } from '@/components/graph/useForceGraph'
import { type GraphData } from '@/lib/graph-types'

// 兼容历史引用路径：这些图谱类型过去由本文件导出，现统一定义于 lib/graph-types。
export type { GraphData, GraphEdge, GraphNode } from '@/lib/graph-types'

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
  const [selected, setSelected] = useState<Selected>(null)
  const [expandedLoops, setExpandedLoops] = useState<Set<string>>(new Set())
  // 大图默认关闭边标签，避免标签过密拖慢渲染
  const [showEdgeLabels, setShowEdgeLabels] = useState(true)

  // 模拟结束提示：监听 isSimulating 由 true → false 的跳变
  const [showFinishedHint, setShowFinishedHint] = useState(false)
  const wasSimulatingRef = useRef(false)
  useEffect(() => {
    if (wasSimulatingRef.current && !isSimulating) setShowFinishedHint(true)
    wasSimulatingRef.current = !!isSimulating
  }, [isSimulating])

  // d3 力导向渲染引擎（仿真/缩放/拖拽/曲边/标签/自适配）收拢在 hook 内。
  const { svgRef, containerRef, typeColors } = useForceGraph({
    graphData,
    showEdgeLabels,
    onSelect: setSelected,
    t,
  })

  const nodeCount = graphData?.nodes?.length ?? 0
  const edgeCount = graphData?.edges?.length ?? 0

  // 切到大图时自动关闭边标签
  useEffect(() => {
    setShowEdgeLabels(edgeCount <= 80)
  }, [edgeCount, graphData])

  // 选中项变化时收起所有自环展开项
  useEffect(() => {
    setExpandedLoops(new Set())
  }, [selected])

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
      {hasData && (
        <GraphLegend typeColors={typeColors} nodeCount={nodeCount} edgeCount={edgeCount} />
      )}

      <svg ref={svgRef} className="text-foreground h-full w-full" />

      {/* 实时更新提示 */}
      {hasData && hint && <GraphRealtimeHint hint={hint} />}

      {/* 模拟结束提示（可关闭） */}
      {!hint && showFinishedHint && (
        <div className="bg-background/95 absolute bottom-4 left-1/2 z-10 flex max-w-[90%] -translate-x-1/2 items-center gap-2 rounded-full border px-4 py-2 text-xs shadow-lg backdrop-blur">
          <Info className="h-3.5 w-3.5 shrink-0 text-amber-500" />
          <span>{t('graph.pendingContentHint')}</span>
          <button
            onClick={() => setShowFinishedHint(false)}
            title={t('graph.closeHint')}
            className="text-muted-foreground hover:text-foreground -mr-1 ml-1 shrink-0"
          >
            <X className="h-3.5 w-3.5" />
          </button>
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
        <GraphDetailShell
          title={selected.kind === 'node' ? t('graph.nodeDetails') : t('graph.relationship')}
          badge={
            selected.kind === 'node'
              ? { label: selected.entityType, color: selected.color }
              : undefined
          }
          onClose={() => setSelected(null)}
        >
          {selected.kind === 'node' ? (
            <NodeDetail data={selected.data} t={t} />
          ) : (
            <EdgeDetail data={selected.data} expanded={expandedLoops} onToggle={toggleLoop} t={t} />
          )}
        </GraphDetailShell>
      )}
    </div>
  )
}
