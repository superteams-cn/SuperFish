import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Step1GraphBuild } from '@/components/Step1GraphBuild'
import { WorkflowLayout, type WorkflowStatus } from '@/components/WorkflowLayout'
import {
  generateOntology,
  getProject,
  buildGraph,
  getTaskStatus,
  getGraphData,
} from '@/lib/api/graph'
import { usePolling } from '@/hooks/usePolling'
import { useDedupedLog } from '@/hooks/useDedupedLog'
import { getPendingUpload, clearPendingUpload } from '@/stores/pendingUpload'
import type {
  BuildProgress,
  GraphData,
  OntologyProgress,
  ProjectData,
  SystemLog,
} from '@/lib/process-types'

export default function ProcessPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const stepNames = t('main.stepNames', { returnObjects: true }) as string[]

  // 本页只承载 Step1（图谱构建）；进入环境搭建由 Step1 直接跳转到 /simulation 路由

  // —— 数据状态 ——
  const [projectData, setProjectData] = useState<ProjectData | null>(null)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [currentPhase, setCurrentPhase] = useState(-1) // -1 上传 / 0 本体 / 1 构建 / 2 完成
  const [ontologyProgress, setOntologyProgress] = useState<OntologyProgress | null>(null)
  const [buildProgress, setBuildProgress] = useState<BuildProgress | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [error, setError] = useState('')
  const [systemLogs, setSystemLogs] = useState<SystemLog[]>([])

  // —— 可变引用（用于轮询闭包）——
  const projectIdRef = useRef<string>(projectId ?? '')
  // 任务轮询当前的 taskId（usePolling 回调无参，经 ref 读取）
  const pollingTaskIdRef = useRef<string | null>(null)
  // 两路轮询回调存 ref，供 usePolling 取最新实现
  const pollTaskRef = useRef<() => void | Promise<void>>(() => {})
  const fetchGraphRef = useRef<() => void | Promise<void>>(() => {})
  const initedRef = useRef(false)
  // 构建消息日志去重（替代手写 buildMsgRef 比较）
  const buildMsgDedup = useDedupedLog<string | undefined>(undefined)
  // 上次图谱数据签名（节点:边），用于跳过无变化的刷新，避免无谓重渲染
  const lastGraphSigRef = useRef<string>('')

  // 两路轮询：任务状态 @2000、图谱数据 @4000；均在 start 时立即拉一次
  const taskPoll = usePolling(() => pollTaskRef.current(), 2000)
  const graphPoll = usePolling(() => fetchGraphRef.current(), 4000, { immediate: true })
  // 通过 ref 引用 startBuildGraph，打破 handleMissingTask ↔ startBuildGraph 的循环依赖
  const startBuildGraphRef = useRef<((force?: boolean) => Promise<void>) | null>(null)

  const addLog = useCallback((msg: string) => {
    const now = new Date()
    const time =
      now.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }) +
      '.' +
      now.getMilliseconds().toString().padStart(3, '0')
    setSystemLogs((prev) => {
      const next = [...prev, { time, msg }]
      return next.length > 100 ? next.slice(next.length - 100) : next
    })
  }, [])

  const stopPolling = useCallback(() => {
    taskPoll.stop()
  }, [taskPoll])

  const stopGraphPolling = useCallback(() => {
    // 仅在确有在跑时打「已停止」日志（等价原 `if (graphPollTimer.current)` 守卫）
    if (graphPoll.isActive()) {
      graphPoll.stop()
      addLog(t('log.graphPollingStopped'))
    }
  }, [addLog, graphPoll, t])

  const loadGraph = useCallback(
    async (graphId: string) => {
      setGraphLoading(true)
      addLog(t('log.loadingFullGraphData', { id: graphId }))
      try {
        const res = await getGraphData(graphId)
        if (res.success) {
          setGraphData(res.data)
          addLog(t('log.graphDataLoadSuccess'))
        } else {
          addLog(t('log.graphDataLoadFailed', { error: res.error || t('common.unknownError') }))
        }
      } catch (e) {
        addLog(t('log.graphDataLoadException', { error: (e as Error).message }))
      } finally {
        setGraphLoading(false)
      }
    },
    [addLog, t],
  )

  const fetchGraphData = useCallback(async () => {
    try {
      const projRes = await getProject(projectIdRef.current)
      if (projRes.success && projRes.data.graph_id) {
        const gRes = await getGraphData(projRes.data.graph_id)
        if (gRes.success) {
          const nodeCount = gRes.data.node_count || gRes.data.nodes?.length || 0
          const edgeCount = gRes.data.edge_count || gRes.data.edges?.length || 0
          const sig = `${nodeCount}:${edgeCount}`
          // 数据无变化则跳过：不更新 state、不打日志，避免 GraphPanel 重跑布局/重置缩放
          if (sig !== lastGraphSigRef.current) {
            lastGraphSigRef.current = sig
            setGraphData(gRes.data)
            addLog(t('log.graphDataRefreshed', { nodes: nodeCount, edges: edgeCount }))
          }
        }
      }
    } catch (e) {
      console.warn(t('log.graphFetchError', { error: (e as Error).message }))
    }
  }, [addLog, t])

  const startGraphPolling = useCallback(() => {
    addLog(t('log.graphPollingStarted'))
    graphPoll.start() // immediate: true → 立即拉一次后按 4000 轮询
  }, [addLog, graphPoll, t])

  const handleMissingTask = useCallback(
    async (taskId: string) => {
      stopPolling()
      try {
        const projRes = await getProject(projectIdRef.current)
        if (projRes.success && projRes.data.status === 'graph_completed' && projRes.data.graph_id) {
          stopGraphPolling()
          setProjectData(projRes.data)
          setCurrentPhase(2)
          addLog(t('log.buildTaskMissingGraphCompleted'))
          await loadGraph(projRes.data.graph_id)
        } else if (projRes.success && projRes.data.status === 'graph_building') {
          // 后台任务随服务端重启丢失（任务仅存于内存），但项目仍处于构建中：
          // 先展示已增量落库的部分图谱，再自动以 force 续建直至完成。
          setProjectData(projRes.data)
          setCurrentPhase(1)
          addLog(t('log.buildTaskLostAutoResume', { taskId }))
          if (projRes.data.graph_id) await fetchGraphData()
          await startBuildGraphRef.current?.(true)
        } else {
          stopGraphPolling()
          setError(t('main.buildInterrupted'))
          addLog(t('log.buildTaskMissingInterrupted', { taskId }))
        }
      } catch (err) {
        setError((err as Error).message)
      }
    },
    [addLog, fetchGraphData, loadGraph, stopGraphPolling, stopPolling, t],
  )

  const pollTaskStatus = useCallback(
    async (taskId: string) => {
      try {
        const res = await getTaskStatus(taskId)
        if (res.success) {
          const task = res.data
          // isNew 无条件调用以更新「上次值」（含 undefined），等价原先的无条件赋值；仅在有内容时打日志
          const msgIsNew = buildMsgDedup.isNew(task.message)
          if (task.message && msgIsNew) {
            addLog(task.message)
          }
          setBuildProgress({ progress: task.progress || 0, message: task.message })

          if (task.status === 'completed') {
            addLog(t('log.graphBuildTaskCompleted'))
            stopPolling()
            stopGraphPolling()
            setCurrentPhase(2)
            const projRes = await getProject(projectIdRef.current)
            if (projRes.success && projRes.data.graph_id) {
              setProjectData(projRes.data)
              await loadGraph(projRes.data.graph_id)
            }
          } else if (task.status === 'failed') {
            stopPolling()
            setError(task.error ?? '')
            addLog(t('log.graphBuildTaskFailed', { error: task.error || t('common.unknownError') }))
          }
        }
      } catch (e) {
        const err = e as { response?: { status?: number } }
        if (err?.response?.status === 404) {
          await handleMissingTask(taskId)
        } else {
          console.error(e)
        }
      }
    },
    [addLog, buildMsgDedup, handleMissingTask, loadGraph, stopGraphPolling, stopPolling, t],
  )

  const startPollingTask = useCallback(
    (taskId: string) => {
      pollingTaskIdRef.current = taskId
      void pollTaskStatus(taskId) // 立即拉一次（保留原行为）
      taskPoll.start()
    },
    [pollTaskStatus, taskPoll],
  )

  // 让 usePolling 的稳定回调始终指向最新实现；任务轮询从 ref 读当前 taskId
  fetchGraphRef.current = fetchGraphData
  pollTaskRef.current = () => {
    const id = pollingTaskIdRef.current
    if (id) void pollTaskStatus(id)
  }

  const startBuildGraph = useCallback(
    async (force = false) => {
      try {
        setCurrentPhase(1)
        setError('')
        setBuildProgress({ progress: 0, message: t('log.startingBuild') })
        addLog(force ? t('log.resumingGraphBuild') : t('log.initiatingGraphBuild'))
        const res = await buildGraph({ project_id: projectIdRef.current, force })
        if (res.success) {
          addLog(t('log.graphBuildTaskStarted', { taskId: res.data.task_id }))
          startGraphPolling()
          startPollingTask(res.data.task_id)
        } else {
          setError(res.error ?? '')
          addLog(t('log.errorStartingBuild', { error: res.error || t('common.unknownError') }))
        }
      } catch (err) {
        setError((err as Error).message)
        addLog(t('log.exceptionInStartBuildGraph', { error: (err as Error).message }))
      }
    },
    [addLog, startGraphPolling, startPollingTask, t],
  )

  // 保持 ref 指向最新的 startBuildGraph，供 handleMissingTask 续建调用
  useEffect(() => {
    startBuildGraphRef.current = startBuildGraph
  }, [startBuildGraph])

  const handleNewProject = useCallback(async () => {
    const pending = getPendingUpload()
    if (!pending.isPending || pending.files.length === 0) {
      setError(t('main.noPendingFiles'))
      addLog(t('log.noPendingFilesRedirect'))
      setTimeout(() => navigate('/', { replace: true }), 1500)
      return
    }
    try {
      setCurrentPhase(0)
      setOntologyProgress({ message: t('log.uploadingAnalyzingDocs') })
      addLog(t('log.startingOntologyGeneration'))
      const formData = new FormData()
      pending.files.forEach((f) => formData.append('files', f))
      formData.append('simulation_requirement', pending.simulationRequirement)
      formData.append('kind', pending.kind)
      formData.append('narrative_mode', pending.narrativeMode)
      const res = await generateOntology(formData)
      if (res.success) {
        clearPendingUpload()
        projectIdRef.current = res.data.project_id
        setProjectData(res.data)
        navigate(`/process/${res.data.project_id}`, { replace: true })
        setOntologyProgress(null)
        addLog(t('log.ontologyGeneratedForProject', { projectId: res.data.project_id }))
        await startBuildGraph()
      } else {
        setError(res.error || t('log.ontologyGenerationFailed'))
      }
    } catch (err) {
      setError((err as Error).message)
    }
  }, [addLog, navigate, startBuildGraph, t])

  const loadProject = useCallback(async () => {
    try {
      addLog(t('log.loadingProject', { projectId: projectIdRef.current }))
      const res = await getProject(projectIdRef.current)
      if (!res.success) {
        setError(res.error ?? '')
        return
      }
      setProjectData(res.data)
      const status = res.data.status
      addLog(t('log.projectLoadedStatus', { status }))
      if (status === 'ontology_generated' && !res.data.graph_id) {
        await startBuildGraph()
      } else if (status === 'graph_building' && res.data.graph_build_task_id) {
        setCurrentPhase(1)
        startPollingTask(res.data.graph_build_task_id)
        startGraphPolling()
      } else if (status === 'graph_building') {
        // 构建中但 task_id 丢失（服务重启，任务仅存内存）：提示并以 force 续建已落库图谱，避免静默卡住
        setCurrentPhase(1)
        addLog(t('log.buildTaskLostAutoResume', { taskId: res.data.graph_build_task_id || '-' }))
        await startBuildGraph(true)
      } else if (status === 'graph_completed' && res.data.graph_id) {
        setCurrentPhase(2)
        await loadGraph(res.data.graph_id)
      } else if (status === 'created' || status === 'ontology_generated') {
        setCurrentPhase(0)
      } else if (status === 'failed') {
        setError(t('log.projectFailed'))
      }
    } catch (err) {
      setError((err as Error).message)
    }
  }, [addLog, loadGraph, startBuildGraph, startGraphPolling, startPollingTask, t])

  // 初始化（仅一次）
  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    addLog(t('log.projectViewInit'))
    if (projectIdRef.current === 'new') {
      void handleNewProject()
    } else {
      void loadProject()
    }
    return () => {
      stopPolling()
      stopGraphPolling()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshGraph = () => {
    if (projectData?.graph_id) {
      addLog(t('log.manualGraphRefresh'))
      void loadGraph(projectData.graph_id)
    }
  }

  // —— 状态指示 ——
  const statusVariant: WorkflowStatus = error
    ? 'error'
    : currentPhase >= 2
      ? 'completed'
      : 'processing'
  const statusText = error
    ? t('common.error')
    : currentPhase >= 2
      ? t('workflowStatus.ready')
      : currentPhase === 1
        ? t('workflowStatus.buildingGraph')
        : currentPhase === 0
          ? t('workflowStatus.generatingOntology')
          : t('workflowStatus.initializing')

  return (
    <WorkflowLayout
      step={1}
      stepName={stepNames?.[0]}
      statusText={statusText}
      statusVariant={statusVariant}
      graphData={graphData}
      graphLoading={graphLoading}
      onRefreshGraph={refreshGraph}
      journeyIds={{ projectId }}
    >
      <Step1GraphBuild
        currentPhase={currentPhase}
        projectData={projectData}
        ontologyProgress={ontologyProgress}
        buildProgress={buildProgress}
        graphData={graphData}
        systemLogs={systemLogs}
        onRebuild={() => startBuildGraph(true)}
      />
    </WorkflowLayout>
  )
}
