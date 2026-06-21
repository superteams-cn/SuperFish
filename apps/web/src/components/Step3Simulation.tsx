import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2, Sparkles, ArrowRight, Code, Radio, AlertTriangle, RotateCcw } from 'lucide-react'

import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { Button } from '@/components/ui/button'
import { CollapsibleHeader } from '@/components/ui/collapsible-header'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { TooltipProvider } from '@/components/ui/tooltip'
import { PlatformStatusCard } from '@/components/step3/PlatformStatusCard'
import { LiveActionItem } from '@/components/step3/LiveActionItem'
import { useSimulationRun } from '@/components/step3/useSimulationRun'
import { StageIcon } from '@/components/common/StageIcon'
import { SoftProgress } from '@/components/common/SoftProgress'
import { TextButton } from '@/components/ui/text-button'
import { stopSimulation } from '@/lib/api/simulation'
import { generateReport } from '@/lib/api/report'
import type { SystemLog } from '@/lib/process-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

interface Step3Props {
  simulationId: string
  maxRounds: number | null
  minutesPerRound: number
  systemLogs: SystemLog[]
  addLog: (msg: string) => void
  onUpdateStatus: (s: WorkflowStatus) => void
}

const TWITTER_ACTIONS = ['POST', 'LIKE', 'REPOST', 'QUOTE', 'FOLLOW', 'IDLE']
const REDDIT_ACTIONS = [
  'POST',
  'COMMENT',
  'LIKE',
  'DISLIKE',
  'SEARCH',
  'TREND',
  'FOLLOW',
  'MUTE',
  'REFRESH',
  'IDLE',
]

/** 步骤三：模拟运行（双平台进度 + 实时动作时间线 + 生成报告）。 */
export function Step3Simulation({
  simulationId,
  maxRounds,
  minutesPerRound,
  systemLogs,
  addLog,
  onUpdateStatus,
}: Step3Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  // 双平台运行状态 + 实时动作流两路轮询、恢复/启动状态机收拢在编排 hook 内。
  const {
    phase,
    runStatus,
    meaningfulActions,
    feedActions,
    elapsed,
    markCompleted,
    startError,
    retry,
  } = useSimulationRun({ simulationId, maxRounds, minutesPerRound, addLog, onUpdateStatus })

  // 纯视图态
  const [isGeneratingReport, setIsGeneratingReport] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false)
  const [backstageOpen, setBackstageOpen] = useState(false)

  const handleGenerateReport = async () => {
    if (!simulationId || isGeneratingReport) return
    setIsGeneratingReport(true)
    addLog(t('log.startingReportGen'))
    try {
      // 不强制重生成：若该模拟已有完成的报告，后端直接返回它 → 仅打开展示
      const res = await generateReport({ simulation_id: simulationId, force_regenerate: false })
      if (res.success && res.data) {
        const reportId = res.data.report_id
        addLog(
          res.data.already_generated
            ? t('log.openingExistingReport', { reportId })
            : t('log.reportGenTaskStarted', { reportId }),
        )
        navigate(`/report/${reportId}`)
      } else {
        addLog(t('log.reportGenFailed', { error: res.error || t('common.unknownError') }))
        setIsGeneratingReport(false)
      }
    } catch (err) {
      addLog(t('log.reportGenException', { error: (err as Error).message }))
      setIsGeneratingReport(false)
    }
  }

  // 停止模拟：终止运行但保留已产生的动作与结果，随后可生成报告
  const handleStopSimulation = async () => {
    if (!simulationId || isStopping) return
    setStopConfirmOpen(false)
    setIsStopping(true)
    addLog(t('log.stoppingSim'))
    try {
      const res = await stopSimulation({ simulation_id: simulationId })
      if (res.success) {
        addLog(t('log.simStoppedSuccess'))
        markCompleted()
      } else {
        addLog(t('log.stopFailed', { error: res.error || t('common.unknownError') }))
      }
    } catch (err) {
      addLog(t('log.stopException', { error: (err as Error).message }))
    } finally {
      setIsStopping(false)
    }
  }

  const totalRounds = runStatus.total_rounds || maxRounds || '-'
  const done = phase === 2
  const interactions = meaningfulActions.length

  // 软进度：双平台轮次推进（结束直接 100）
  const tot = Number(runStatus.total_rounds || maxRounds || 0)
  const cur = (runStatus.twitter_current_round || 0) + (runStatus.reddit_current_round || 0)
  const softProgress = done ? 100 : tot > 0 ? Math.min(Math.round((cur / (2 * tot)) * 100), 99) : 6

  // 启动被阻断（如并发配额已满）：用明确的错误态替代乐观「登场」动画，附重试入口。
  const blocked = !!startError

  return (
    <TooltipProvider delayDuration={150}>
      <div className="relative flex h-full flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8">
          <div className="mx-auto max-w-2xl">
            {blocked ? (
              <div className="animate-rise-in mx-auto mt-6 max-w-md text-center">
                <div className="bg-destructive/10 text-destructive mx-auto flex h-14 w-14 items-center justify-center rounded-full">
                  <AlertTriangle className="h-7 w-7" />
                </div>
                <h2 className="mt-4 text-xl font-semibold tracking-tight">
                  {t('step3.cStartBlocked')}
                </h2>
                <p className="text-muted-foreground mt-2 text-sm leading-relaxed">{startError}</p>
                <Button
                  variant="outline"
                  className="mt-5 gap-2 rounded-full px-6"
                  onClick={() => void retry()}
                >
                  <RotateCcw className="h-4 w-4" />
                  {t('step3.cRetry')}
                </Button>
              </div>
            ) : (
              <>
                {/* 舞台标题 */}
                <div className="animate-rise-in text-center">
                  <StageIcon done={done} />
                  <h2 className="text-2xl font-semibold tracking-tight">
                    {done ? t('step3.cActed') : t('step3.cActing')}
                  </h2>
                  <p className="text-muted-foreground mt-2">
                    {done ? t('step3.cActedDone', { count: interactions }) : t('step3.cActingSub')}
                  </p>
                </div>

                {/* 进展：软进度 + 互动计数 */}
                <div className="mt-6">
                  <p className="text-muted-foreground mb-2 text-center text-sm">
                    {t('step3.cInteractions', { count: interactions })}
                  </p>
                  <SoftProgress value={softProgress} floor={6} />
                </div>

                {/* 完成 → 给你结论 CTA；运行中 → 提前结束 */}
                <div className="animate-rise-in mt-7 flex flex-col items-center gap-3">
                  {done ? (
                    <Button
                      variant="gradient"
                      className="h-12 gap-2 rounded-full px-8 text-base"
                      onClick={handleGenerateReport}
                      disabled={isGeneratingReport}
                    >
                      {isGeneratingReport ? (
                        <Loader2 className="h-5 w-5 animate-spin" />
                      ) : (
                        <Sparkles className="h-5 w-5" />
                      )}
                      {isGeneratingReport ? t('step3.cGenerating') : t('step3.cNext')}
                      {!isGeneratingReport && <ArrowRight className="h-5 w-5" />}
                    </Button>
                  ) : (
                    <TextButton
                      onClick={() => setStopConfirmOpen(true)}
                      disabled={isStopping}
                      className="text-xs"
                    >
                      {t('step3.cStopEarly')}
                    </TextButton>
                  )}
                </div>

                {/* 实况流（人话）：谁·做了什么·内容 */}
                <div className="mt-8">
                  {feedActions.length > 0 ? (
                    <div className="space-y-3">
                      {feedActions.map((action) => (
                        <LiveActionItem key={action._uniqueId || action.id} action={action} />
                      ))}
                    </div>
                  ) : (
                    <div className="text-muted-foreground flex h-40 flex-col items-center justify-center gap-3 text-sm">
                      <Radio className="h-6 w-6 animate-pulse text-indigo-500" />
                      {t('step3.cWaiting')}
                    </div>
                  )}
                </div>
              </>
            )}

            {/* 幕后：双平台技术状态 / 原始日志 */}
            <div className="mt-10">
              <CollapsibleHeader
                open={backstageOpen}
                onToggle={() => setBackstageOpen((o) => !o)}
                icon={<Code className="h-4 w-4" />}
                label={t('step3.cBackstage')}
                hint={t('step3.cBackstageHint')}
              />

              {backstageOpen && (
                <div className="mt-3 space-y-4">
                  <div className="flex gap-3">
                    <PlatformStatusCard
                      name={t('step3.platformTwitterName')}
                      platform="twitter"
                      running={runStatus.twitter_running}
                      completed={runStatus.twitter_completed}
                      currentRound={runStatus.twitter_current_round || 0}
                      totalRounds={totalRounds}
                      elapsedTime={elapsed(runStatus.twitter_current_round)}
                      actionsCount={runStatus.twitter_actions_count || 0}
                      availableActions={TWITTER_ACTIONS}
                    />
                    <PlatformStatusCard
                      name={t('step3.platformRedditName')}
                      platform="reddit"
                      running={runStatus.reddit_running}
                      completed={runStatus.reddit_completed}
                      currentRound={runStatus.reddit_current_round || 0}
                      totalRounds={totalRounds}
                      elapsedTime={elapsed(runStatus.reddit_current_round)}
                      actionsCount={runStatus.reddit_actions_count || 0}
                      availableActions={REDDIT_ACTIONS}
                    />
                  </div>
                  <SystemLogTerminal logs={systemLogs} badge={simulationId || 'NO_SIMULATION'} />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 停止确认 */}
      <Dialog open={stopConfirmOpen} onOpenChange={setStopConfirmOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('step3.stopConfirmTitle')}</DialogTitle>
            <DialogDescription>{t('step3.stopConfirmDesc')}</DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setStopConfirmOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button variant="destructive" onClick={handleStopSimulation}>
              {t('step3.cStopEarly')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  )
}
