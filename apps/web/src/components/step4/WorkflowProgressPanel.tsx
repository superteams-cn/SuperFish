import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { AgentLogEntry, ReportOutline } from '@/lib/step4-types'

interface Props {
  logs: AgentLogEntry[]
  outline: ReportOutline | null
  generatedSections: Record<number, string>
  currentSectionIndex: number | null
  isComplete: boolean
}

type StepStatus = 'done' | 'active' | 'todo'

/** 工作流进度面板：指标卡（章节/耗时/工具调用数）+ 步骤时间线。 */
export function WorkflowProgressPanel({
  logs,
  outline,
  generatedSections,
  currentSectionIndex,
  isComplete,
}: Props) {
  const { t } = useTranslation()

  const totalSections = outline?.sections?.length || 0
  const completedSections = Object.keys(generatedSections).length
  const totalToolCalls = logs.filter((l) => l.action === 'tool_call').length

  const elapsedText = useMemo(() => {
    const last = logs[logs.length - 1]
    const elapsed = last?.elapsed_seconds || 0
    if (elapsed < 60) return `${Math.round(elapsed)}s`
    const mins = Math.floor(elapsed / 60)
    const secs = Math.round(elapsed % 60)
    return `${mins}m ${secs}s`
  }, [logs])

  const isPlanningStarted = logs.some(
    (l) => l.action === 'planning_start' || l.action === 'report_start',
  )
  const isPlanningDone =
    !!outline?.sections?.length || logs.some((l) => l.action === 'planning_complete')
  const isFinalizing =
    !isComplete && isPlanningDone && totalSections > 0 && completedSections >= totalSections

  const activeSectionIndex = useMemo(() => {
    if (isComplete) return null
    if (currentSectionIndex) return currentSectionIndex
    if (totalSections > 0 && completedSections < totalSections) return completedSections + 1
    return null
  }, [isComplete, currentSectionIndex, totalSections, completedSections])

  const steps = useMemo(() => {
    const out: { key: string; noLabel: string; title: string; status: StepStatus }[] = []
    out.push({
      key: 'planning',
      noLabel: 'PL',
      title: t('step4.stepPlanning'),
      status: isPlanningDone ? 'done' : isPlanningStarted ? 'active' : 'todo',
    })
    ;(outline?.sections || []).forEach((section, i) => {
      const idx = i + 1
      const status: StepStatus =
        isComplete || generatedSections[idx]
          ? 'done'
          : activeSectionIndex === idx
            ? 'active'
            : 'todo'
      out.push({
        key: `section-${idx}`,
        noLabel: String(idx).padStart(2, '0'),
        title: section.title,
        status,
      })
    })
    out.push({
      key: 'complete',
      noLabel: 'OK',
      title: t('step4.stepComplete'),
      status: isComplete ? 'done' : isFinalizing ? 'active' : 'todo',
    })
    return out
  }, [
    t,
    outline,
    generatedSections,
    isComplete,
    isPlanningDone,
    isPlanningStarted,
    isFinalizing,
    activeSectionIndex,
  ])

  const statusBadge = isComplete
    ? { variant: 'default' as const, text: t('common.completed') }
    : logs.length > 0
      ? { variant: 'secondary' as const, text: t('workflowStatus.generating') }
      : { variant: 'outline' as const, text: t('step4.statusWaiting') }

  return (
    <div className="space-y-3">
      {/* 指标卡 */}
      <div className="grid grid-cols-3 gap-2">
        <Metric label={t('step4.metricSections')} value={`${completedSections}/${totalSections}`} />
        <Metric label={t('step4.metricElapsed')} value={elapsedText} />
        <Metric label={t('step4.metricTools')} value={String(totalToolCalls)} />
      </div>

      <div className="flex justify-end">
        <Badge variant={statusBadge.variant} className="text-[10px]">
          {statusBadge.text}
        </Badge>
      </div>

      {/* 步骤时间线 */}
      <div className="border-muted ml-1 space-y-0 border-l pl-3">
        {steps.map((step) => (
          <div key={step.key} className="relative py-1">
            <span
              className={cn(
                'border-background absolute -left-[18px] top-2 h-2 w-2 rounded-full border-2',
                step.status === 'done'
                  ? 'bg-green-500'
                  : step.status === 'active'
                    ? 'bg-brand animate-pulse'
                    : 'bg-muted-foreground/30',
              )}
            />
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground font-mono text-[10px]">{step.noLabel}</span>
              <span
                className={cn(
                  'text-[11px]',
                  step.status === 'todo' ? 'text-muted-foreground' : 'text-foreground',
                  step.status === 'active' && 'font-semibold',
                )}
              >
                {step.title}
              </span>
              {step.status === 'active' && (
                <span className="text-brand text-[9px] font-medium uppercase">
                  {t('step4.inProgress')}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card rounded-md border p-2 text-center">
      <div className="font-mono text-sm font-semibold">{value}</div>
      <div className="text-muted-foreground text-[10px]">{label}</div>
    </div>
  )
}
