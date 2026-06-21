import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { startSimulation, getRunStatus, getRunStatusDetail } from '@/lib/api/simulation'
import type { ActionItem, RunStatus } from '@/lib/step3-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

interface Options {
  simulationId: string
  maxRounds: number | null
  minutesPerRound: number
  addLog: (msg: string) => void
  onUpdateStatus: (s: WorkflowStatus) => void
}

/**
 * 步骤三模拟运行的编排逻辑：双平台运行状态 + 实时动作流两路轮询 + 进入时的恢复或启动。
 *
 * 收拢计时器、动作去重 ref、轮询回调与生命周期副作用；Step3Simulation 仅消费返回的
 * 状态做渲染，并用 stopPolling / markCompleted 实现「提前结束」。行为与原内联实现一致。
 */
export function useSimulationRun({
  simulationId,
  maxRounds,
  minutesPerRound,
  addLog,
  onUpdateStatus,
}: Options) {
  const { t } = useTranslation()

  const [phase, setPhase] = useState(0) // 0 未开始 / 1 运行中 / 2 已完成
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

  // 实况流只展示有意义的互动（过滤「无操作」噪声）；最新的在最上
  const meaningfulActions = useMemo(
    () => actions.filter((a) => a.action_type !== 'DO_NOTHING'),
    [actions],
  )
  const feedActions = useMemo(() => meaningfulActions.slice(-80).reverse(), [meaningfulActions])

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

  // 「提前结束」成功后：停轮询、置完成态。供组件的停止处理器调用。
  const markCompleted = useCallback(() => {
    setPhase(2)
    stopPolling()
    onUpdateStatus('completed')
  }, [onUpdateStatus, stopPolling])

  return {
    phase,
    runStatus,
    meaningfulActions,
    feedActions,
    elapsed,
    markCompleted,
  }
}
