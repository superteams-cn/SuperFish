import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, Network, Columns2, PanelRight, MoreHorizontal } from 'lucide-react'

import { GraphPanel, type GraphData } from '@/components/GraphPanel'
import { GraphPanelG6 } from '@/components/GraphPanelG6'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { Brand } from '@/components/common/Brand'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

export type ViewMode = 'graph' | 'split' | 'workbench'
export type GraphEngine = 'd3' | 'g6'
export type WorkflowStatus = 'processing' | 'completed' | 'error'

interface WorkflowLayoutProps {
  /** 当前步骤序号（1-5） */
  step: number
  /** 步骤名称（旧字段，旅程进度已替代，保留兼容） */
  stepName?: string
  /** 状态文案（旧字段，保留兼容） */
  statusText?: string
  /** 状态样式（旧字段，保留兼容） */
  statusVariant?: WorkflowStatus
  graphData: GraphData | null
  graphLoading?: boolean
  onRefreshGraph?: () => void
  /** 初始布局模式，默认 split */
  initialViewMode?: ViewMode
  /** 右侧工作区内容 */
  children: ReactNode
}

/**
 * 工作流通用外壳：顶部「推演旅程」进度（4 阶段人话）+ 左侧图谱舞台 + 右侧工作区。
 * 视图切换（图谱/分屏/内容）保留在顶栏；引擎切换（D3/G6）收进「更多」菜单（高级）。
 */
export function WorkflowLayout({
  step,
  graphData,
  graphLoading,
  onRefreshGraph,
  initialViewMode = 'split',
  children,
}: WorkflowLayoutProps) {
  const { t } = useTranslation()
  const [viewMode, setViewMode] = useState<ViewMode>(initialViewMode)
  const [engine, setEngine] = useState<GraphEngine>('d3')

  const toggleMaximize = (target: ViewMode) => setViewMode((v) => (v === target ? 'split' : target))

  const leftWidth =
    viewMode === 'graph' ? 'w-full' : viewMode === 'workbench' ? 'w-0 opacity-0' : 'w-1/2'
  const rightWidth =
    viewMode === 'workbench' ? 'w-full' : viewMode === 'graph' ? 'w-0 opacity-0' : 'w-1/2'

  // 5 个工程步骤 → 4 个旅程阶段（step5 归入"给你结论"）
  const stages = [t('home.jStage1'), t('home.jStage2'), t('home.jStage3'), t('home.jStage4')]
  const currentIdx = Math.min(Math.max(step - 1, 0), stages.length - 1)

  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      {/* 顶部：品牌 + 旅程进度 + 视图/更多/主题/语言 */}
      <header className="glass-subtle relative z-10 flex h-14 items-center justify-between border-b border-white/30 px-5 dark:border-white/10">
        <Brand />

        <div className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-2 lg:flex">
          {stages.map((label, i) => (
            <div key={label} className="flex items-center gap-2">
              {i > 0 && <span className="bg-border h-px w-5" />}
              <span
                className={cn(
                  'flex items-center gap-1.5 text-sm transition-colors',
                  i === currentIdx ? 'text-foreground font-medium' : 'text-muted-foreground',
                )}
              >
                {i < currentIdx ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                ) : i === currentIdx ? (
                  <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
                ) : (
                  <span className="bg-muted-foreground/30 h-2 w-2 rounded-full" />
                )}
                {label}
              </span>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          {/* 视图切换（图谱 / 分屏 / 内容） */}
          <ToggleGroup
            type="single"
            value={viewMode}
            onValueChange={(v) => v && setViewMode(v as ViewMode)}
            className="hidden md:flex"
          >
            <ToggleGroupItem value="graph" title={t('main.layoutGraph')} className="px-2.5">
              <Network className="h-4 w-4" />
            </ToggleGroupItem>
            <ToggleGroupItem value="split" title={t('main.layoutSplit')} className="px-2.5">
              <Columns2 className="h-4 w-4" />
            </ToggleGroupItem>
            <ToggleGroupItem value="workbench" title={t('main.layoutWorkbench')} className="px-2.5">
              <PanelRight className="h-4 w-4" />
            </ToggleGroupItem>
          </ToggleGroup>

          {/* 更多（引擎切换，高级） */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" size="icon" className="rounded-full">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setEngine((e) => (e === 'g6' ? 'd3' : 'g6'))}>
                {engine === 'g6' ? t('graph.engineSwitchToD3') : t('graph.engineSwitchToG6')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <ThemeSwitcher />
          <LanguageSwitcher />
        </div>
      </header>

      {/* 内容区：左图谱舞台 + 右工作区 */}
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
