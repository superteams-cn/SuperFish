import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { GraphPanel } from '@/components/GraphPanel'
import { Step1GraphBuild } from '@/components/Step1GraphBuild'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { PagePlaceholder } from '@/components/PagePlaceholder'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '@/lib/api/graph'
import { getPendingUpload, clearPendingUpload } from '@/stores/pendingUpload'
import type {
  BuildProgress,
  GraphData,
  OntologyProgress,
  ProjectData,
  SystemLog,
} from '@/lib/process-types'
import { cn } from '@/lib/utils'

type ViewMode = 'graph' | 'split' | 'workbench'

export default function ProcessPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const stepNames = t('main.stepNames', { returnObjects: true }) as string[]

  // —— 布局与步骤 ——
  const [viewMode, setViewMode] = useState<ViewMode>('split')
  // 本页只承载 Step1（图谱构建）；进入环境搭建由 Step1 直接跳转到 /simulation 路由
  const currentStep = 1

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

  const addLog = useCallback((msg: string) => {
    const now = new Date()
    const time =
      now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) +
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
    graphPollTimer.current = setInterval(fetchGraphData, 10000)
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
        } else {
          stopGraphPolling()
          setError(t('main.buildInterrupted'))
          addLog(`Build task ${taskId} not found and graph not completed — build was interrupted.`)
        }
      } catch (err) {
        setError((err as Error).message)
      }
    },
    [addLog, loadGraph, stopGraphPolling, stopPolling, t],
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
            setError(task.error)
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

  const startBuildGraph = useCallback(async () => {
    try {
      setCurrentPhase(1)
      setBuildProgress({ progress: 0, message: 'Starting build...' })
      addLog('Initiating graph build...')
      const res = await buildGraph({ project_id: projectIdRef.current })
      if (res.success) {
        addLog(`Graph build task started. Task ID: ${res.data.task_id}`)
        startGraphPolling()
        startPollingTask(res.data.task_id)
      } else {
        setError(res.error)
        addLog(`Error starting build: ${res.error}`)
      }
    } catch (err) {
      setError((err as Error).message)
      addLog(`Exception in startBuildGraph: ${(err as Error).message}`)
    }
  }, [addLog, startGraphPolling, startPollingTask])

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
        setError(res.error)
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

  const toggleMaximize = (target: ViewMode) => {
    setViewMode((v) => (v === target ? 'split' : target))
  }

  // —— 状态指示 ——
  const statusText = error
    ? 'Error'
    : currentPhase >= 2
      ? 'Ready'
      : currentPhase === 1
        ? 'Building Graph'
        : currentPhase === 0
          ? 'Generating Ontology'
          : 'Initializing'
  const statusColor = error ? 'bg-red-500' : currentPhase >= 2 ? 'bg-green-500' : 'bg-[#FF5722] animate-pulse'

  const leftWidth = viewMode === 'graph' ? 'w-full' : viewMode === 'workbench' ? 'w-0 opacity-0' : 'w-1/2'
  const rightWidth = viewMode === 'workbench' ? 'w-full' : viewMode === 'graph' ? 'w-0 opacity-0' : 'w-1/2'

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* 头部 */}
      <header className="relative z-10 flex h-[60px] items-center justify-between border-b px-6">
        <div
          className="cursor-pointer font-mono text-lg font-extrabold tracking-wide"
          onClick={() => navigate('/')}
        >
          SUPERFISH
        </div>

        <div className="absolute left-1/2 -translate-x-1/2">
          <div className="flex gap-1 rounded-md bg-muted p-1">
            {(['graph', 'split', 'workbench'] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={cn(
                  'rounded px-4 py-1.5 text-xs font-semibold transition',
                  viewMode === mode ? 'bg-background shadow' : 'text-muted-foreground',
                )}
              >
                {{ graph: t('main.layoutGraph'), split: t('main.layoutSplit'), workbench: t('main.layoutWorkbench') }[mode]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <ThemeSwitcher />
          <LanguageSwitcher />
          <div className="h-3.5 w-px bg-border" />
          <div className="flex items-center gap-2 text-sm">
            <span className="font-mono font-bold text-muted-foreground">Step {currentStep}/5</span>
            <span className="font-bold">{stepNames?.[currentStep - 1]}</span>
          </div>
          <div className="h-3.5 w-px bg-border" />
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className={cn('h-2 w-2 rounded-full', statusColor)} />
            {statusText}
          </span>
        </div>
      </header>

      {/* 内容区 */}
      <main className="relative flex flex-1 overflow-hidden">
        <div className={cn('h-full overflow-hidden border-r transition-all duration-300', leftWidth)}>
          <GraphPanel
            graphData={graphData}
            loading={graphLoading}
            onRefresh={refreshGraph}
            onToggleMaximize={() => toggleMaximize('graph')}
          />
        </div>
        <div className={cn('h-full overflow-hidden transition-all duration-300', rightWidth)}>
          {currentStep === 1 ? (
            <Step1GraphBuild
              currentPhase={currentPhase}
              projectData={projectData}
              ontologyProgress={ontologyProgress}
              buildProgress={buildProgress}
              graphData={graphData}
              systemLogs={systemLogs}
            />
          ) : (
            <PagePlaceholder title={stepNames?.[currentStep - 1] ?? '环境搭建'} />
          )}
        </div>
      </main>
    </div>
  )
}
