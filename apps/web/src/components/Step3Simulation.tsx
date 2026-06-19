import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'

import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { Button } from '@/components/ui/button'
import { PlatformStatusCard } from '@/components/step3/PlatformStatusCard'
import { ActionCard } from '@/components/step3/ActionCard'
import { startSimulation, getRunStatus, getRunStatusDetail } from '@/lib/api/simulation'
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
        statusTimer.current = setInterval(fetchRunStatus, 2000)
        detailTimer.current = setInterval(fetchRunStatusDetail, 3000)
      } else {
        addLog(t('log.startFailed', { error: res.error || t('common.unknownError') }))
        onUpdateStatus('error')
      }
    } catch (err) {
      addLog(t('log.startException', { error: (err as Error).message }))
      onUpdateStatus('error')
    }
  }, [
    addLog,
    fetchRunStatus,
    fetchRunStatusDetail,
    maxRounds,
    onUpdateStatus,
    simulationId,
    stopPolling,
    t,
  ])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    addLog(t('log.step3Init'))
    if (simulationId) void doStart()
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

  const totalRounds = runStatus.total_rounds || maxRounds || '-'

  return (
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
        <Button onClick={handleGenerateReport} disabled={phase !== 2 || isGeneratingReport}>
          {isGeneratingReport && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {isGeneratingReport ? t('step3.generatingReportBtn') : t('step3.startGenerateReportBtn')}
          {!isGeneratingReport && <span>→</span>}
        </Button>
      </div>

      {/* 动作时间线 */}
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
        <div className="border-muted space-y-2 border-l pl-1">
          {actions.map((action) => (
            <ActionCard key={action._uniqueId || action.id} action={action} />
          ))}
        </div>
        {actions.length === 0 && (
          <div className="text-muted-foreground flex h-40 flex-col items-center justify-center gap-2 text-sm">
            <span className="h-3 w-3 animate-ping rounded-full bg-[#FF5722]" />
            {t('step3.waitingForActions')}
          </div>
        )}
      </div>

      <SystemLogTerminal logs={systemLogs} badge={simulationId || 'NO_SIMULATION'} />
    </div>
  )
}
