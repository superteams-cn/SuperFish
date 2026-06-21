import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  prepareSimulation,
  getPrepareStatus,
  getSimulation,
  getSimulationProfilesRealtime,
  getSimulationConfigRealtime,
} from '@/lib/api/simulation'
import { usePolling } from '@/hooks/usePolling'
import { useDedupedLog } from '@/hooks/useDedupedLog'
import type { Profile, SimulationConfig } from '@/lib/step2-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

interface Options {
  simulationId: string
  addLog: (msg: string) => void
  onUpdateStatus: (status: WorkflowStatus) => void
  /** 推演类型：narrative 时跳过 OASIS 人设/配置门控，准备完成即就绪。 */
  kind?: 'social_opinion' | 'narrative'
}

/**
 * 步骤二环境搭建的编排逻辑：准备 / 人设 / 配置 三路轮询 + 进入时的恢复或启动状态机。
 *
 * 把所有计时器、可变 ref、轮询回调与生命周期副作用收拢于此，Step2EnvSetup 仅消费
 * 返回的状态（phase/profiles/config…）与 startPrepare 句柄做渲染。行为与原内联实现一致。
 */
export function useStep2Orchestration({ simulationId, addLog, onUpdateStatus, kind }: Options) {
  const { t } = useTranslation()
  const isNarrative = kind === 'narrative'

  const [phase, setPhase] = useState(0) // 0 初始化 / 1 人设 / 2 配置 / 4 完成
  const [taskId, setTaskId] = useState<string | null>(null)
  const [prepareProgress, setPrepareProgress] = useState(0)
  const [currentStage, setCurrentStage] = useState('')
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [expectedTotal, setExpectedTotal] = useState<number | null>(null)
  const [simulationConfig, setSimulationConfig] = useState<SimulationConfig | null>(null)

  // 三路轮询回调存 ref，供 usePolling 取最新实现（打破定义顺序的循环依赖）
  const pollPrepareRef = useRef<() => void | Promise<void>>(() => {})
  const fetchProfilesRef = useRef<() => void | Promise<void>>(() => {})
  const fetchConfigRef = useRef<() => void | Promise<void>>(() => {})
  const taskIdRef = useRef<string | null>(null)
  const profilesRef = useRef<Profile[]>([])
  const expectedRef = useRef<number | null>(null)
  const initedRef = useRef(false)
  // 日志去重（替代手写 lastMsg/lastProfileCount/lastConfigStage 的「记上次值再比较」）
  const msgDedup = useDedupedLog<string>('')
  const profileCountDedup = useDedupedLog<number>(0)
  const configStageDedup = useDedupedLog<string>('')

  // 三路轮询：准备状态 @2000、人设 @3000、配置 @2000
  const preparePoll = usePolling(() => pollPrepareRef.current(), 2000)
  const profilesPoll = usePolling(() => fetchProfilesRef.current(), 3000)
  const configPoll = usePolling(() => fetchConfigRef.current(), 2000)

  const stopPolling = useCallback(() => preparePoll.stop(), [preparePoll])
  const stopProfilesPolling = useCallback(() => profilesPoll.stop(), [profilesPoll])
  const stopConfigPolling = useCallback(() => configPoll.stop(), [configPoll])

  const fetchProfilesRealtime = useCallback(async () => {
    if (!simulationId) return
    try {
      const res = await getSimulationProfilesRealtime(simulationId, 'reddit')
      if (res.success && res.data) {
        const list: Profile[] = res.data.profiles || []
        profilesRef.current = list
        setProfiles(list)
        if (res.data.total_expected) {
          expectedRef.current = res.data.total_expected
          setExpectedTotal(res.data.total_expected)
        }
        const count = list.length
        if (count > 0 && profileCountDedup.isNew(count)) {
          const total = expectedRef.current || '?'
          const latest = list[count - 1]
          const name = latest?.name || latest?.username || `Agent_${count}`
          if (count === 1) addLog(t('log.startGeneratingAgentProfiles'))
          addLog(
            t('log.agentProfile', {
              current: count,
              total,
              name,
              profession: latest?.profession || t('step2.unknownProfession'),
            }),
          )
          if (expectedRef.current && count >= expectedRef.current) {
            addLog(t('log.allProfilesComplete', { count }))
          }
        }
      }
    } catch (err) {
      console.warn('获取 Profiles 失败:', err)
    }
  }, [addLog, profileCountDedup, simulationId, t])

  const fetchConfigRealtime = useCallback(async () => {
    if (!simulationId) return
    try {
      const res = await getSimulationConfigRealtime(simulationId)
      if (!res.success || !res.data) return
      const data = res.data
      if (data.generation_stage && configStageDedup.isNew(data.generation_stage)) {
        if (data.generation_stage === 'generating_profiles')
          addLog(t('log.generatingAgentProfileConfig'))
        else if (data.generation_stage === 'generating_config') addLog(t('log.generatingLLMConfig'))
      }
      if (data.config_generated && data.config) {
        setSimulationConfig(data.config)
        addLog(t('log.configComplete'))
        if (data.summary) {
          addLog(t('log.configSummaryAgents', { count: data.summary.total_agents }))
          addLog(t('log.configSummaryHours', { hours: data.summary.simulation_hours }))
          addLog(t('log.configSummaryPosts', { count: data.summary.initial_posts_count }))
          addLog(t('log.configSummaryTopics', { count: data.summary.hot_topics_count }))
          addLog(
            t('log.configSummaryPlatforms', {
              twitter: data.summary.has_twitter_config ? '✓' : '✗',
              reddit: data.summary.has_reddit_config ? '✓' : '✗',
            }),
          )
        }
        stopConfigPolling()
        setPhase(4)
        addLog(t('log.envSetupComplete'))
        onUpdateStatus('completed')
      }
    } catch (err) {
      console.warn('获取 Config 失败:', err)
    }
  }, [addLog, configStageDedup, onUpdateStatus, simulationId, stopConfigPolling, t])

  const startConfigPolling = useCallback(() => {
    // 已在轮询则不重复启动、不重复打日志（等价原 `if (configTimer.current) return`）
    if (configPoll.isActive()) return
    addLog(t('log.startGeneratingConfig'))
    configPoll.start()
  }, [addLog, configPoll, t])

  const loadPreparedData = useCallback(async () => {
    // 剧本推演：无 OASIS 人设/配置，准备完成即就绪，直接放行到 Step3。
    if (isNarrative) {
      addLog(t('narrative.envReady'))
      setPhase(4)
      onUpdateStatus('completed')
      return
    }
    setPhase(2)
    addLog(t('log.loadingExistingConfig'))
    await fetchProfilesRealtime()
    addLog(t('log.loadedAgentProfiles', { count: profilesRef.current.length }))
    try {
      const res = await getSimulationConfigRealtime(simulationId)
      if (res.success && res.data) {
        if (res.data.config_generated && res.data.config) {
          setSimulationConfig(res.data.config)
          addLog(t('log.configLoadSuccess'))
          if (res.data.summary) {
            addLog(t('log.configSummaryAgents', { count: res.data.summary.total_agents }))
            addLog(t('log.configSummaryHours', { hours: res.data.summary.simulation_hours }))
            addLog(t('log.configSummaryPostsAlt', { count: res.data.summary.initial_posts_count }))
          }
          addLog(t('log.envSetupComplete'))
          setPhase(4)
          onUpdateStatus('completed')
        } else {
          addLog(t('log.configGenerating'))
          startConfigPolling()
        }
      }
    } catch (err) {
      addLog(t('log.loadConfigFailed', { error: (err as Error).message }))
      onUpdateStatus('error')
    }
  }, [
    addLog,
    fetchProfilesRealtime,
    isNarrative,
    onUpdateStatus,
    simulationId,
    startConfigPolling,
    t,
  ])

  const pollPrepareStatus = useCallback(async () => {
    if (!taskIdRef.current && !simulationId) return
    try {
      const res = await getPrepareStatus({
        task_id: taskIdRef.current,
        simulation_id: simulationId,
      })
      if (!res.success || !res.data) return
      const data = res.data
      setPrepareProgress(data.progress || 0)

      if (data.progress_detail) {
        const detail = data.progress_detail
        setCurrentStage(detail.current_stage_name || '')
        const logKey = `${detail.current_stage}-${detail.current_item}-${detail.total_items}`
        if (detail.item_description && msgDedup.isNew(logKey)) {
          const stageInfo = `[${detail.stage_index}/${detail.total_stages}]`
          addLog(
            (detail.total_items ?? 0) > 0
              ? `${stageInfo} ${detail.current_stage_name}: ${detail.current_item}/${detail.total_items} - ${detail.item_description}`
              : `${stageInfo} ${detail.current_stage_name}: ${detail.item_description}`,
          )
        }
      } else if (data.message) {
        const match = data.message.match(/\[(\d+)\/(\d+)\]\s*([^:]+)/)
        if (match) setCurrentStage(match[3].trim())
        if (msgDedup.isNew(data.message)) {
          addLog(data.message)
        }
      }

      if (data.status === 'completed' || data.status === 'ready' || data.already_prepared) {
        addLog(t('log.prepareComplete'))
        stopPolling()
        stopProfilesPolling()
        await loadPreparedData()
      } else if (data.status === 'failed') {
        addLog(t('log.prepareFailedWithError', { error: data.error || t('common.unknownError') }))
        stopPolling()
        stopProfilesPolling()
      }
    } catch (err) {
      console.warn('轮询状态失败:', err)
    }
  }, [addLog, loadPreparedData, msgDedup, simulationId, stopPolling, stopProfilesPolling, t])

  // 让 usePolling 的稳定回调始终指向最新的 fetch 实现
  pollPrepareRef.current = pollPrepareStatus
  fetchProfilesRef.current = fetchProfilesRealtime
  fetchConfigRef.current = fetchConfigRealtime

  const startPrepare = useCallback(
    async (force = false) => {
      if (!simulationId) {
        addLog(t('log.errorMissingSimId'))
        onUpdateStatus('error')
        return
      }
      setPhase(1)
      addLog(t('log.simInstanceCreated', { id: simulationId }))
      addLog(t('log.preparingSimEnv'))
      onUpdateStatus('processing')
      try {
        const res = await prepareSimulation({
          simulation_id: simulationId,
          use_llm_for_profiles: true,
          parallel_profile_count: 5,
          force_regenerate: force,
        })
        if (res.success && res.data) {
          if (res.data.already_prepared) {
            addLog(t('log.detectedExistingPrep'))
            await loadPreparedData()
            return
          }
          taskIdRef.current = res.data.task_id ?? null
          setTaskId(res.data.task_id ?? null)
          addLog(t('log.prepareTaskStarted'))
          addLog(t('log.prepareTaskId', { taskId: res.data.task_id }))
          if (res.data.expected_entities_count) {
            expectedRef.current = res.data.expected_entities_count
            setExpectedTotal(res.data.expected_entities_count)
            addLog(t('log.graphEntitiesFound', { count: res.data.expected_entities_count }))
            if (res.data.entity_types?.length) {
              addLog(t('log.entityTypes', { types: res.data.entity_types.join(', ') }))
            }
          }
          addLog(t('log.startPollingProgress'))
          preparePoll.start()
          profilesPoll.start()
        } else {
          addLog(t('log.prepareFailed', { error: res.error || t('common.unknownError') }))
          onUpdateStatus('error')
        }
      } catch (err) {
        addLog(t('log.prepareException', { error: (err as Error).message }))
        onUpdateStatus('error')
      }
    },
    [addLog, loadPreparedData, onUpdateStatus, preparePoll, profilesPoll, simulationId, t],
  )

  // 阶段切换：进入配置生成阶段时启动配置轮询
  useEffect(() => {
    if (currentStage === '生成Agent人设' || currentStage === 'generating_profiles') {
      setPhase((p) => (p < 1 ? 1 : p))
    } else if (currentStage === '生成模拟配置' || currentStage === 'generating_config') {
      setPhase((p) => (p < 2 ? 2 : p))
      startConfigPolling()
    }
  }, [currentStage, startConfigPolling])

  // 进入/刷新时：先查后端真实状态再决定，避免无脑重新触发 prepare（后端 /prepare 对进行中不去重）。
  const resumeOrStart = useCallback(async () => {
    addLog(t('log.step2Init'))
    if (!simulationId) return

    let state: import('@/lib/api/types').SimulationData | null = null
    try {
      const res = await getSimulation(simulationId)
      if (res.success && res.data) state = res.data
    } catch {
      // 拉状态失败 → 下面回退到首次准备
    }

    const status = state?.status

    // 已准备完成 → 直接加载结果，不触发 prepare
    if (status === 'ready' || state?.config_generated) {
      await loadPreparedData()
      return
    }

    // 准备进行中 → 仅恢复轮询（按 simulationId，不依赖内存 task_id），不重复触发
    if (status === 'preparing') {
      setPhase(1)
      addLog(t('log.resumingPrepare'))
      onUpdateStatus('processing')
      if (state?.entities_count) {
        expectedRef.current = state.entities_count
        setExpectedTotal(state.entities_count)
      }
      await fetchProfilesRealtime()
      preparePoll.start()
      profilesPoll.start()
      return
    }

    // created / failed / 无记录 → 才（重新）启动准备
    void startPrepare(false)
  }, [
    addLog,
    fetchProfilesRealtime,
    loadPreparedData,
    onUpdateStatus,
    preparePoll,
    profilesPoll,
    simulationId,
    startPrepare,
    t,
  ])

  // 挂载时恢复或启动（仅一次）
  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    if (simulationId) void resumeOrStart()
    return () => {
      stopPolling()
      stopProfilesPolling()
      stopConfigPolling()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    phase,
    taskId,
    prepareProgress,
    profiles,
    expectedTotal,
    simulationConfig,
    startPrepare,
  }
}
