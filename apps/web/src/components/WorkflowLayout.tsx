import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { GraphPanel, type GraphData } from '@/components/GraphPanel'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
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
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [viewMode, setViewMode] = useState<ViewMode>(initialViewMode)

  const toggleMaximize = (target: ViewMode) => setViewMode((v) => (v === target ? 'split' : target))

  const statusColor =
    statusVariant === 'error'
      ? 'bg-red-500'
      : statusVariant === 'completed'
        ? 'bg-green-500'
        : 'bg-[#FF5722] animate-pulse'

  const leftWidth =
    viewMode === 'graph' ? 'w-full' : viewMode === 'workbench' ? 'w-0 opacity-0' : 'w-1/2'
  const rightWidth =
    viewMode === 'workbench' ? 'w-full' : viewMode === 'graph' ? 'w-0 opacity-0' : 'w-1/2'

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* 头部 */}
      <header className="relative z-10 flex h-[60px] items-center justify-between border-b px-6">
        <div
          className="cursor-pointer font-mono text-lg font-extrabold tracking-wide"
          onClick={() => navigate('/')}
        >
          SUPERFISH
        </div>

        <div className="absolute left-1/2 -translate-x-1/2">
          <div className="flex gap-1 rounded-md bg-muted p-1">
            {(['graph', 'split', 'workbench'] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={cn(
                  'rounded px-4 py-1.5 text-xs font-semibold transition',
                  viewMode === mode ? 'bg-background shadow' : 'text-muted-foreground',
                )}
              >
                {
                  {
                    graph: t('main.layoutGraph'),
                    split: t('main.layoutSplit'),
                    workbench: t('main.layoutWorkbench'),
                  }[mode]
                }
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <ThemeSwitcher />
          <LanguageSwitcher />
          <div className="h-3.5 w-px bg-border" />
          <div className="flex items-center gap-2 text-sm">
            <span className="font-mono font-bold text-muted-foreground">Step {step}/5</span>
            {stepName && <span className="font-bold">{stepName}</span>}
          </div>
          <div className="h-3.5 w-px bg-border" />
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className={cn('h-2 w-2 rounded-full', statusColor)} />
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
