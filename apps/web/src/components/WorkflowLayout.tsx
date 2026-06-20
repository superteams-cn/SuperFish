import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Share2, Workflow } from 'lucide-react'

import { GraphPanel, type GraphData } from '@/components/GraphPanel'
import { GraphPanelG6 } from '@/components/GraphPanelG6'
import { Button } from '@/components/ui/button'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { Brand } from '@/components/common/Brand'
import { StatusDot } from '@/components/common/StatusDot'
import { Separator } from '@/components/ui/separator'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'

export type ViewMode = 'graph' | 'split' | 'workbench'
export type GraphEngine = 'd3' | 'g6'
export type WorkflowStatus = 'processing' | 'completed' | 'error'

interface WorkflowLayoutProps {
  /** 当前步骤序号（1-5） */
  step: number
  /** 步骤名称 */
  stepName?: string
  /** 状态文案 */
  statusText: string
  /** 状态样式 */
  statusVariant: WorkflowStatus
  graphData: GraphData | null
  graphLoading?: boolean
  onRefreshGraph?: () => void
  /** 初始布局模式，默认 split */
  initialViewMode?: ViewMode
  /** 右侧工作区内容 */
  children: ReactNode
}

/**
 * 工作流通用布局外壳：顶部品牌/视图切换/步骤指示/状态，
 * 左侧知识图谱面板，右侧步骤工作区。Process / Simulation 等页面复用。
 */
export function WorkflowLayout({
  step,
  stepName,
  statusText,
  statusVariant,
  graphData,
  graphLoading,
  onRefreshGraph,
  initialViewMode = 'split',
  children,
}: WorkflowLayoutProps) {
  const { t } = useTranslation()
  const [viewMode, setViewMode] = useState<ViewMode>(initialViewMode)
  const [engine, setEngine] = useState<GraphEngine>('g6')

  const toggleMaximize = (target: ViewMode) => setViewMode((v) => (v === target ? 'split' : target))

  const leftWidth =
    viewMode === 'graph' ? 'w-full' : viewMode === 'workbench' ? 'w-0 opacity-0' : 'w-1/2'
  const rightWidth =
    viewMode === 'workbench' ? 'w-full' : viewMode === 'graph' ? 'w-0 opacity-0' : 'w-1/2'

  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      {/* 头部 */}
      <header className="glass-subtle relative z-10 flex h-[60px] items-center justify-between border-b border-white/30 px-6 dark:border-white/10">
        <Brand />

        <ToggleGroup
          type="single"
          value={viewMode}
          onValueChange={(v) => v && setViewMode(v as ViewMode)}
          className="absolute left-1/2 -translate-x-1/2"
        >
          <ToggleGroupItem value="graph">{t('main.layoutGraph')}</ToggleGroupItem>
          <ToggleGroupItem value="split">{t('main.layoutSplit')}</ToggleGroupItem>
          <ToggleGroupItem value="workbench">{t('main.layoutWorkbench')}</ToggleGroupItem>
        </ToggleGroup>

        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setEngine((e) => (e === 'g6' ? 'd3' : 'g6'))}
            title={engine === 'g6' ? t('graph.engineSwitchToD3') : t('graph.engineSwitchToG6')}
          >
            {engine === 'g6' ? <Share2 className="h-4 w-4" /> : <Workflow className="h-4 w-4" />}
          </Button>
          <ThemeSwitcher />
          <LanguageSwitcher />
          <Separator orientation="vertical" className="h-3.5" />
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground font-mono font-bold">Step {step}/5</span>
            {stepName && <span className="font-bold">{stepName}</span>}
          </div>
          <Separator orientation="vertical" className="h-3.5" />
          <span className="text-muted-foreground flex items-center gap-2 text-xs">
            <StatusDot variant={statusVariant} />
            {statusText}
          </span>
        </div>
      </header>

      {/* 内容区 */}
      <main className="relative flex flex-1 overflow-hidden">
        <div
          className={cn('h-full overflow-hidden border-r transition-all duration-300', leftWidth)}
        >
          {engine === 'g6' ? (
            <GraphPanelG6
              graphData={graphData}
              loading={graphLoading}
              onRefresh={onRefreshGraph}
              onToggleMaximize={() => toggleMaximize('graph')}
              resizeKey={viewMode}
            />
          ) : (
            <GraphPanel
              graphData={graphData}
              loading={graphLoading}
              onRefresh={onRefreshGraph}
              onToggleMaximize={() => toggleMaximize('graph')}
            />
          )}
        </div>
        <div className={cn('h-full overflow-hidden transition-all duration-300', rightWidth)}>
          {children}
        </div>
      </main>
    </div>
  )
}
