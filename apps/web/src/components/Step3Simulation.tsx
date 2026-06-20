import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2, Square } from 'lucide-react'

import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { TooltipProvider } from '@/components/ui/tooltip'
import { PlatformStatusCard } from '@/components/step3/PlatformStatusCard'
import { DualTimeline } from '@/components/step3/DualTimeline'
import {
  startSimulation,
  stopSimulation,
  getRunStatus,
  getRunStatusDetail,
} from '@/lib/api/simulation'
import { generateReport } from '@/lib/api/report'
import type { SystemLog } from '@/lib/process-types'
import type { ActionItem, RunStatus } from '@/lib/step3-types'
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

  const [phase, setPhase] = useState(0) // 0 未开始 / 1 运行中 / 2 已完成
  const [isGeneratingReport, setIsGeneratingReport] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false)
  const [runStatus, setRunStatus] = useState<RunStatus>({})
  const [actions, setActions] = useState<ActionItem[]>([])

  const statusTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const detailTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const actionIds = useRef<Set<string>>(new Set())
  const prevTwitter = useRef(0)
  const prevReddit = useRef(0)
  const initedRef = useRef(false)

  const elapsed = useCallback(
    (round?: number) => {
      if (!round || round <= 0) return '0h 0m'
      const total = round * minutesPerRound
      return `${Math.floor(total / 60)}h ${total % 60}m`
    },
    [minutesPerRound],
  )

  const twitterCount = useMemo(
    () => actions.filter((a) => a.platform === 'twitter').length,
    [actions],
  )
  const redditCount = useMemo(
    () => actions.filter((a) => a.platform === 'reddit').length,
    [actions],
  )

  const stopPolling = useCallback(() => {
    if (statusTimer.current) clearInterval(statusTimer.current)
    if (detailTimer.current) clearInterval(detailTimer.current)
    statusTimer.current = null
    detailTimer.current = null
  }, [])

  const startPolling = useCallback(() => {
    stopPolling()
    statusTimer.current = setInterval(fetchRunStatus, 2000)
    detailTimer.current = setInterval(fetchRunStatusDetail, 3000)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopPolling])

  const checkPlatformsCompleted = (data: RunStatus) => {
    if (!data) return false
    const tc = data.twitter_completed === true
    const rc = data.reddit_completed === true
    const te = (data.twitter_actions_count ?? 0) > 0 || data.twitter_running || tc
    const re = (data.reddit_actions_count ?? 0) > 0 || data.reddit_running || rc
    if (!te && !re) return false
    if (te && !tc) return false
    if (re && !rc) return false
    return true
  }

  const fetchRunStatus = useCallback(async () => {
    if (!simulationId) return
    try {
      const res = await getRunStatus(simulationId)
      if (!res.success || !res.data) return
      const data: RunStatus = res.data
      setRunStatus(data)

      if ((data.twitter_current_round ?? 0) > prevTwitter.current) {
        addLog(
          `[Plaza] R${data.twitter_current_round}/${data.total_rounds} | T:${data.twitter_simulated_hours || 0}h | A:${data.twitter_actions_count}`,
        )
        prevTwitter.current = data.twitter_current_round ?? 0
      }
      if ((data.reddit_current_round ?? 0) > prevReddit.current) {
        addLog(
          `[Community] R${data.reddit_current_round}/${data.total_rounds} | T:${data.reddit_simulated_hours || 0}h | A:${data.reddit_actions_count}`,
        )
        prevReddit.current = data.reddit_current_round ?? 0
      }

      const isCompleted = data.runner_status === 'completed' || data.runner_status === 'stopped'
      const platformsCompleted = checkPlatformsCompleted(data)
      if (isCompleted || platformsCompleted) {
        if (platformsCompleted && !isCompleted) addLog(t('log.allPlatformsCompleted'))
        addLog(t('log.simCompleted'))
        setPhase(2)
        stopPolling()
        onUpdateStatus('completed')
      }
    } catch (err) {
      console.warn('获取运行状态失败:', err)
    }
  }, [addLog, onUpdateStatus, simulationId, stopPolling, t])

  const fetchRunStatusDetail = useCallback(async () => {
    if (!simulationId) return
    try {
      const res = await getRunStatusDetail(simulationId)
      if (!res.success || !res.data) return
      const serverActions: ActionItem[] = res.data.all_actions || []
      const fresh: ActionItem[] = []
      serverActions.forEach((action) => {
        const id =
          action.id ||
          `${action.timestamp}-${action.platform}-${action.agent_id}-${action.action_type}`
        if (!actionIds.current.has(id)) {
          actionIds.current.add(id)
          fresh.push({ ...action, _uniqueId: id })
        }
      })
      if (fresh.length) setActions((prev) => [...prev, ...fresh])
    } catch (err) {
      console.warn('获取详细状态失败:', err)
    }
  }, [simulationId])

  const doStart = useCallback(async () => {
    if (!simulationId) {
      addLog(t('log.errorMissingSimId'))
      return
    }
    // 重置
    setPhase(0)
    setRunStatus({})
    setActions([])
    actionIds.current = new Set()
    prevTwitter.current = 0
    prevReddit.current = 0
    stopPolling()

    addLog(t('log.startingDualSim'))
    onUpdateStatus('processing')
    try {
      const params: Record<string, unknown> = {
        simulation_id: simulationId,
        platform: 'parallel',
        force: true,
        enable_graph_memory_update: true,
      }
      if (maxRounds) {
        params.max_rounds = maxRounds
        addLog(t('log.setMaxRounds', { rounds: maxRounds }))
      }
      addLog(t('log.graphMemoryUpdateEnabled'))
      const res = await startSimulation(params)
      if (res.success && res.data) {
        if (res.data.force_restarted) addLog(t('log.oldSimCleared'))
        addLog(t('log.engineStarted'))
        addLog(`  ├─ PID: ${res.data.process_pid || '-'}`)
        setPhase(1)
        setRunStatus(res.data)
        startPolling()
      } else {
        addLog(t('log.startFailed', { error: res.error || t('common.unknownError') }))
        onUpdateStatus('error')
      }
    } catch (err) {
      addLog(t('log.startException', { error: (err as Error).message }))
      onUpdateStatus('error')
    }
  }, [addLog, startPolling, maxRounds, onUpdateStatus, simulationId, stopPolling, t])

  // 进入页面/刷新时：先查后端真实状态再决定，避免无脑 force 重启把进行中的模拟从第0轮重来。
  const resumeOrStart = useCallback(async () => {
    addLog(t('log.step3Init'))
    if (!simulationId) return

    let data: RunStatus | null = null
    try {
      const res = await getRunStatus(simulationId)
      if (res.success && res.data) data = res.data
    } catch {
      // 拉状态失败，下面回退到首次启动
    }

    const status = data?.runner_status

    // 运行中：仅恢复监控，不重启、不清日志/进度
    if (status === 'running' || status === 'starting') {
      addLog(t('log.resumingSim'))
      setPhase(1)
      setRunStatus(data!)
      prevTwitter.current = data!.twitter_current_round ?? 0
      prevReddit.current = data!.reddit_current_round ?? 0
      onUpdateStatus('processing')
      void fetchRunStatusDetail()
      startPolling()
      return
    }

    // 已结束：载入最终结果，进入可生成报告态
    if (status === 'completed' || status === 'stopped') {
      addLog(t('log.simAlreadyCompleted'))
      setPhase(2)
      setRunStatus(data!)
      void fetchRunStatusDetail()
      onUpdateStatus('completed')
      return
    }

    // 上次失败：提示错误但仍允许重新启动（页面无独立启动按钮）
    if (status === 'failed') {
      addLog(t('log.simPreviouslyFailed', { error: data?.error || t('common.unknownError') }))
    }

    // ready / idle / 无运行记录 / failed → 首次（或重新）启动
    void doStart()
  }, [addLog, doStart, fetchRunStatusDetail, onUpdateStatus, simulationId, startPolling, t])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    void resumeOrStart()
    return () => stopPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleGenerateReport = async () => {
    if (!simulationId || isGeneratingReport) return
    setIsGeneratingReport(true)
    addLog(t('log.startingReportGen'))
    try {
      const res = await generateReport({ simulation_id: simulationId, force_regenerate: true })
      if (res.success && res.data) {
        const reportId = res.data.report_id
        addLog(t('log.reportGenTaskStarted', { reportId }))
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
        setPhase(2)
        stopPolling()
        onUpdateStatus('completed')
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

  return (
    <TooltipProvider delayDuration={150}>
      <div className="bg-muted/30 flex h-full flex-col overflow-hidden">
        {/* 顶部控制栏 */}
        <div className="bg-card flex items-center gap-3 border-b p-3">
          <div className="flex flex-1 gap-3">
            <PlatformStatusCard
              name={t('step3.platformTwitterName')}
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
              running={runStatus.reddit_running}
              completed={runStatus.reddit_completed}
              currentRound={runStatus.reddit_current_round || 0}
              totalRounds={totalRounds}
              elapsedTime={elapsed(runStatus.reddit_current_round)}
              actionsCount={runStatus.reddit_actions_count || 0}
              availableActions={REDDIT_ACTIONS}
            />
          </div>
          {/* 运行中可停止：保留已产生的结果 */}
          {phase === 1 && (
            <Button
              variant="outline"
              onClick={() => setStopConfirmOpen(true)}
              disabled={isStopping}
            >
              {isStopping ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Square className="h-3.5 w-3.5" />
              )}
              {t('step3.stopSimulation')}
            </Button>
          )}
          <Button onClick={handleGenerateReport} disabled={phase !== 2 || isGeneratingReport}>
            {isGeneratingReport && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {isGeneratingReport
              ? t('step3.generatingReportBtn')
              : t('step3.startGenerateReportBtn')}
            {!isGeneratingReport && <span>→</span>}
          </Button>
        </div>

        {/* 动作时间线（双轨：左信息广场 / 右话题社区，窄屏降级单轨） */}
        <div className="flex-1 overflow-y-auto p-4">
          {actions.length > 0 && (
            <div className="text-muted-foreground mb-3 flex items-center gap-3 text-xs">
              <span>
                {t('step3.totalEvents')}: <span className="font-mono">{actions.length}</span>
              </span>
              <span className="font-mono">
                <span className="text-sky-500">{twitterCount}</span> /{' '}
                <span className="text-orange-500">{redditCount}</span>
              </span>
            </div>
          )}
          {actions.length > 0 ? (
            <DualTimeline actions={actions} />
          ) : (
            <div className="text-muted-foreground flex h-40 flex-col items-center justify-center gap-2 text-sm">
              <span className="bg-brand h-3 w-3 animate-ping rounded-full" />
              {t('step3.waitingForActions')}
            </div>
          )}
        </div>

        <SystemLogTerminal logs={systemLogs} badge={simulationId || 'NO_SIMULATION'} />
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
              {t('step3.stopSimulation')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  )
}
