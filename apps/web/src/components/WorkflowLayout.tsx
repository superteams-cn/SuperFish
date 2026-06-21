import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, Network, Columns2, PanelRight } from 'lucide-react'

import { readJourney, recordStage, stageUrl, type JourneyIds } from '@/lib/journey'

import { GraphPanel, type GraphData } from '@/components/GraphPanel'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { Brand } from '@/components/common/Brand'
import { QuotaChip } from '@/components/common/QuotaChip'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'

export type ViewMode = 'graph' | 'split' | 'workbench'
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
  /** 当前页已知的旅程 ID（项目/模拟/报告），用于驱动进度条上已到达阶段的跳转 */
  journeyIds?: JourneyIds
  /** 右侧工作区内容 */
  children: ReactNode
}

/**
 * 工作流通用外壳：顶部「推演旅程」进度（4 阶段人话）+ 左侧图谱舞台 + 右侧工作区。
 * 视图切换（图谱/分屏/内容）保留在顶栏；图谱统一用 d3 力导向实现。
 */
export function WorkflowLayout({
  step,
  graphData,
  graphLoading,
  onRefreshGraph,
  initialViewMode = 'split',
  journeyIds,
  children,
}: WorkflowLayoutProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<ViewMode>(initialViewMode)

  // 记录当前阶段与已知 ID 到旅程；合并后的旅程驱动进度条跳转
  const [journey, setJourney] = useState(readJourney)
  const idsKey = `${journeyIds?.projectId ?? ''}|${journeyIds?.simulationId ?? ''}|${journeyIds?.reportId ?? ''}`
  useEffect(() => {
    setJourney(recordStage(step, journeyIds ?? {}))
  }, [step, idsKey, journeyIds])

  const toggleMaximize = (target: ViewMode) => setViewMode((v) => (v === target ? 'split' : target))

  const leftWidth =
    viewMode === 'graph' ? 'w-full' : viewMode === 'workbench' ? 'w-0 opacity-0' : 'w-1/2'
  const rightWidth =
    viewMode === 'workbench' ? 'w-full' : viewMode === 'graph' ? 'w-0 opacity-0' : 'w-1/2'

  // 5 个旅程阶段（与 5 个页面一一对应）
  const stages = [
    t('home.jStage1'),
    t('home.jStage2'),
    t('home.jStage3'),
    t('home.jStage4'),
    t('home.jStage5'),
  ]
  const currentIdx = Math.min(Math.max(step - 1, 0), stages.length - 1)

  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      {/* 顶部：品牌 + 旅程进度 + 视图/更多/主题/语言 */}
      <header className="glass-subtle relative z-10 flex h-14 items-center justify-between border-b border-white/30 px-5 dark:border-white/10">
        <Brand />

        <div className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-3 lg:flex">
          {stages.map((label, i) => {
            const stepNo = i + 1
            const done = i < currentIdx
            // 任何「已到达过」(stepNo <= reachedStep) 且非当前、且有目标 URL 的阶段都可点
            const url = stageUrl(stepNo, journey)
            const clickable = stepNo !== step && stepNo <= journey.reachedStep && !!url
            return (
              <div key={label} className="flex items-center gap-3">
                {i > 0 && <span className="bg-border h-px w-10" />}
                <button
                  type="button"
                  disabled={!clickable}
                  onClick={clickable ? () => navigate(url) : undefined}
                  title={clickable ? t('main.goToStage', { stage: label }) : undefined}
                  className={cn(
                    'flex items-center gap-1.5 text-sm transition-colors',
                    i === currentIdx ? 'text-foreground font-medium' : 'text-muted-foreground',
                    clickable && 'hover:text-foreground cursor-pointer',
                    !clickable && 'cursor-default',
                  )}
                >
                  {done ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  ) : i === currentIdx ? (
                    <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
                  ) : (
                    <span className="bg-muted-foreground/30 h-2 w-2 rounded-full" />
                  )}
                  {label}
                </button>
              </div>
            )
          })}
        </div>

        <div className="flex items-center gap-1.5">
          {/* 并发推演名额：顶栏长驻，让用户进入推演前就知道还能不能开 */}
          <QuotaChip />

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

          <ThemeSwitcher />
          <LanguageSwitcher />
        </div>
      </header>

      {/* 内容区：左图谱舞台 + 右工作区 */}
      <main className="relative flex flex-1 overflow-hidden">
        <div
          className={cn('h-full overflow-hidden border-r transition-all duration-300', leftWidth)}
        >
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
