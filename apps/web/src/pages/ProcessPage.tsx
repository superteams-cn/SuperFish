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
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const graphPollTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const initedRef = useRef(false)
  const buildMsgRef = useRef<string | undefined>(undefined)
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
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }, [])

  const stopGraphPolling = useCallback(() => {
    if (graphPollTimer.current) {
      clearInterval(graphPollTimer.current)
      graphPollTimer.current = null
      addLog('Graph polling stopped.')
    }
  }, [addLog])

  const loadGraph = useCallback(
    async (graphId: string) => {
      setGraphLoading(true)
      addLog(`Loading full graph data: ${graphId}`)
      try {
        const res = await getGraphData(graphId)
        if (res.success) {
          setGraphData(res.data)
          addLog('Graph data loaded successfully.')
        } else {
          addLog(`Failed to load graph data: ${res.error}`)
        }
      } catch (e) {
        addLog(`Exception loading graph: ${(e as Error).message}`)
      } finally {
        setGraphLoading(false)
      }
    },
    [addLog],
  )

  const fetchGraphData = useCallback(async () => {
    try {
      const projRes = await getProject(projectIdRef.current)
      if (projRes.success && projRes.data.graph_id) {
        const gRes = await getGraphData(projRes.data.graph_id)
        if (gRes.success) {
          setGraphData(gRes.data)
          const nodeCount = gRes.data.node_count || gRes.data.nodes?.length || 0
          const edgeCount = gRes.data.edge_count || gRes.data.edges?.length || 0
          addLog(`Graph data refreshed. Nodes: ${nodeCount}, Edges: ${edgeCount}`)
        }
      }
    } catch (e) {
      console.warn('Graph fetch error:', e)
    }
  }, [addLog])

  const startGraphPolling = useCallback(() => {
    addLog('Started polling for graph data...')
    void fetchGraphData()
    graphPollTimer.current = setInterval(fetchGraphData, 4000)
  }, [addLog, fetchGraphData])

  const handleMissingTask = useCallback(
    async (taskId: string) => {
      stopPolling()
      try {
        const projRes = await getProject(projectIdRef.current)
        if (projRes.success && projRes.data.status === 'graph_completed' && projRes.data.graph_id) {
          stopGraphPolling()
          setProjectData(projRes.data)
          setCurrentPhase(2)
          addLog('Build task not found, but graph already completed. Loading final graph.')
          await loadGraph(projRes.data.graph_id)
        } else if (projRes.success && projRes.data.status === 'graph_building') {
          // 后台任务随服务端重启丢失（任务仅存于内存），但项目仍处于构建中：
          // 先展示已增量落库的部分图谱，再自动以 force 续建直至完成。
          setProjectData(projRes.data)
          setCurrentPhase(1)
          addLog(`Build task ${taskId} lost (likely server restart). Auto-resuming build...`)
          if (projRes.data.graph_id) await fetchGraphData()
          await startBuildGraphRef.current?.(true)
        } else {
          stopGraphPolling()
          setError(t('main.buildInterrupted'))
          addLog(`Build task ${taskId} not found and graph not completed — build was interrupted.`)
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
          if (task.message && task.message !== buildMsgRef.current) {
            addLog(task.message)
          }
          buildMsgRef.current = task.message
          setBuildProgress({ progress: task.progress || 0, message: task.message })

          if (task.status === 'completed') {
            addLog('Graph build task completed.')
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
            addLog(`Graph build task failed: ${task.error}`)
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
    [addLog, handleMissingTask, loadGraph, stopGraphPolling, stopPolling],
  )

  const startPollingTask = useCallback(
    (taskId: string) => {
      void pollTaskStatus(taskId)
      pollTimer.current = setInterval(() => pollTaskStatus(taskId), 2000)
    },
    [pollTaskStatus],
  )

  const startBuildGraph = useCallback(
    async (force = false) => {
      try {
        setCurrentPhase(1)
        setError('')
        setBuildProgress({ progress: 0, message: 'Starting build...' })
        addLog(force ? 'Resuming graph build (force)...' : 'Initiating graph build...')
        const res = await buildGraph({ project_id: projectIdRef.current, force })
        if (res.success) {
          addLog(`Graph build task started. Task ID: ${res.data.task_id}`)
          startGraphPolling()
          startPollingTask(res.data.task_id)
        } else {
          setError(res.error ?? '')
          addLog(`Error starting build: ${res.error}`)
        }
      } catch (err) {
        setError((err as Error).message)
        addLog(`Exception in startBuildGraph: ${(err as Error).message}`)
      }
    },
    [addLog, startGraphPolling, startPollingTask],
  )

  // 保持 ref 指向最新的 startBuildGraph，供 handleMissingTask 续建调用
  useEffect(() => {
    startBuildGraphRef.current = startBuildGraph
  }, [startBuildGraph])

  const handleNewProject = useCallback(async () => {
    const pending = getPendingUpload()
    if (!pending.isPending || pending.files.length === 0) {
      setError(t('main.noPendingFiles'))
      addLog('Error: No pending files found. Redirecting to home.')
      setTimeout(() => navigate('/', { replace: true }), 1500)
      return
    }
    try {
      setCurrentPhase(0)
      setOntologyProgress({ message: 'Uploading and analyzing docs...' })
      addLog('Starting ontology generation: Uploading files...')
      const formData = new FormData()
      pending.files.forEach((f) => formData.append('files', f))
      formData.append('simulation_requirement', pending.simulationRequirement)
      const res = await generateOntology(formData)
      if (res.success) {
        clearPendingUpload()
        projectIdRef.current = res.data.project_id
        setProjectData(res.data)
        navigate(`/process/${res.data.project_id}`, { replace: true })
        setOntologyProgress(null)
        addLog(`Ontology generated successfully for project ${res.data.project_id}`)
        await startBuildGraph()
      } else {
        setError(res.error || 'Ontology generation failed')
      }
    } catch (err) {
      setError((err as Error).message)
    }
  }, [addLog, navigate, startBuildGraph, t])

  const loadProject = useCallback(async () => {
    try {
      addLog(`Loading project ${projectIdRef.current}...`)
      const res = await getProject(projectIdRef.current)
      if (!res.success) {
        setError(res.error ?? '')
        return
      }
      setProjectData(res.data)
      const status = res.data.status
      addLog(`Project loaded. Status: ${status}`)
      if (status === 'ontology_generated' && !res.data.graph_id) {
        await startBuildGraph()
      } else if (status === 'graph_building' && res.data.graph_build_task_id) {
        setCurrentPhase(1)
        startPollingTask(res.data.graph_build_task_id)
        startGraphPolling()
      } else if (status === 'graph_completed' && res.data.graph_id) {
        setCurrentPhase(2)
        await loadGraph(res.data.graph_id)
      } else if (status === 'created' || status === 'ontology_generated') {
        setCurrentPhase(0)
      } else if (status === 'failed') {
        setError('Project failed')
      }
    } catch (err) {
      setError((err as Error).message)
    }
  }, [addLog, loadGraph, startBuildGraph, startGraphPolling, startPollingTask])

  // 初始化（仅一次）
  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    addLog('Project view initialized.')
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
      addLog('Manual graph refresh triggered.')
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
    ? 'Error'
    : currentPhase >= 2
      ? 'Ready'
      : currentPhase === 1
        ? 'Building Graph'
        : currentPhase === 0
          ? 'Generating Ontology'
          : 'Initializing'

  return (
    <WorkflowLayout
      step={1}
      stepName={stepNames?.[0]}
      statusText={statusText}
      statusVariant={statusVariant}
      graphData={graphData}
      graphLoading={graphLoading}
      onRefreshGraph={refreshGraph}
    >
      <Step1GraphBuild
        currentPhase={currentPhase}
        projectData={projectData}
        ontologyProgress={ontologyProgress}
        buildProgress={buildProgress}
        graphData={graphData}
        systemLogs={systemLogs}
      />
    </WorkflowLayout>
  )
}
