import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { GraphPanel, type GraphData } from '@/components/GraphPanel'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { Brand } from '@/components/common/Brand'
import { StatusDot } from '@/components/common/StatusDot'
import { Separator } from '@/components/ui/separator'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'

export type ViewMode = 'graph' | 'split' | 'workbench'
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

  const toggleMaximize = (target: ViewMode) => setViewMode((v) => (v === target ? 'split' : target))

  const leftWidth =
    viewMode === 'graph' ? 'w-full' : viewMode === 'workbench' ? 'w-0 opacity-0' : 'w-1/2'
  const rightWidth =
    viewMode === 'workbench' ? 'w-full' : viewMode === 'graph' ? 'w-0 opacity-0' : 'w-1/2'

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* 头部 */}
      <header className="relative z-10 flex h-[60px] items-center justify-between border-b px-6">
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
          <ThemeSwitcher />
          <LanguageSwitcher />
          <Separator orientation="vertical" className="h-3.5" />
          <div className="flex items-center gap-2 text-sm">
            <span className="font-mono font-bold text-muted-foreground">Step {step}/5</span>
            {stepName && <span className="font-bold">{stepName}</span>}
          </div>
          <Separator orientation="vertical" className="h-3.5" />
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <StatusDot variant={statusVariant} />
            {statusText}
          </span>
        </div>
      </header>

      {/* 内容区 */}
      <main className="relative flex flex-1 overflow-hidden">
        <div className={cn('h-full overflow-hidden border-r transition-all duration-300', leftWidth)}>
          <GraphPanel
            graphData={graphData}
            loading={graphLoading}
            onRefresh={onRefreshGraph}
            onToggleMaximize={() => toggleMaximize('graph')}
          />
        </div>
        <div className={cn('h-full overflow-hidden transition-all duration-300', rightWidth)}>
          {children}
        </div>
      </main>
    </div>
  )
}
