import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { WorkflowLayout, type WorkflowStatus } from '@/components/WorkflowLayout'
import { Step2EnvSetup } from '@/components/Step2EnvSetup'
import { getProject, getGraphData } from '@/lib/api/graph'
import { getSimulation, stopSimulation, getEnvStatus, closeSimulationEnv } from '@/lib/api/simulation'
import type { GraphData, ProjectData, SystemLog } from '@/lib/process-types'

export default function SimulationPage() {
  const { simulationId = '' } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const stepNames = t('main.stepNames', { returnObjects: true }) as string[]

  const [projectData, setProjectData] = useState<ProjectData | null>(null)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [systemLogs, setSystemLogs] = useState<SystemLog[]>([])
  const [status, setStatus] = useState<WorkflowStatus>('processing')
  const initedRef = useRef(false)

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

  const loadGraph = useCallback(
    async (graphId: string) => {
      setGraphLoading(true)
      try {
        const res = await getGraphData(graphId)
        if (res.success) {
          setGraphData(res.data)
          addLog(t('log.graphDataLoadSuccess'))
        }
      } catch (err) {
        addLog(t('log.graphLoadFailed', { error: (err as Error).message }))
      } finally {
        setGraphLoading(false)
      }
    },
    [addLog, t],
  )

  const refreshGraph = () => {
    if (projectData?.graph_id) void loadGraph(projectData.graph_id)
  }

  // 强制停止模拟
  const forceStop = useCallback(async () => {
    try {
      const res = await stopSimulation({ simulation_id: simulationId })
      addLog(
        res.success
          ? t('log.simForceStopSuccess')
          : t('log.forceStopSimFailed', { error: res.error || t('common.unknownError') }),
      )
    } catch (err) {
      addLog(t('log.forceStopSimException', { error: (err as Error).message }))
    }
  }, [addLog, simulationId, t])

  // 用户从 Step3 返回 Step2 时，关闭仍在运行的模拟
  const checkAndStopRunning = useCallback(async () => {
    if (!simulationId) return
    try {
      const envRes = await getEnvStatus({ simulation_id: simulationId })
      if (envRes.success && envRes.data?.env_alive) {
        addLog(t('log.detectedSimEnvRunning'))
        try {
          const closeRes = await closeSimulationEnv({ simulation_id: simulationId, timeout: 10 })
          if (closeRes.success) {
            addLog(t('log.simEnvClosed'))
          } else {
            addLog(t('log.closeSimEnvFailedWithError', { error: closeRes.error || t('common.unknownError') }))
            await forceStop()
          }
        } catch (closeErr) {
          addLog(t('log.closeSimEnvException', { error: (closeErr as Error).message }))
          await forceStop()
        }
      } else {
        const simRes = await getSimulation(simulationId)
        if (simRes.success && simRes.data?.status === 'running') {
          addLog(t('log.detectedSimRunning'))
          await forceStop()
        }
      }
    } catch (err) {
      console.warn('检查模拟状态失败:', err)
    }
  }, [addLog, forceStop, simulationId, t])

  const loadSimulationData = useCallback(async () => {
    try {
      addLog(t('log.loadingSimData', { id: simulationId }))
      const simRes = await getSimulation(simulationId)
      if (simRes.success && simRes.data) {
        if (simRes.data.project_id) {
          const projRes = await getProject(simRes.data.project_id)
          if (projRes.success && projRes.data) {
            setProjectData(projRes.data)
            addLog(t('log.projectLoadSuccess', { id: projRes.data.project_id }))
            if (projRes.data.graph_id) await loadGraph(projRes.data.graph_id)
          }
        }
      } else {
        addLog(t('log.loadSimDataFailed', { error: simRes.error || t('common.unknownError') }))
      }
    } catch (err) {
      addLog(t('log.loadException', { error: (err as Error).message }))
    }
  }, [addLog, loadGraph, simulationId, t])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    addLog(t('log.simViewInit'))
    void (async () => {
      await checkAndStopRunning()
      await loadSimulationData()
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleGoBack = () => {
    if (projectData?.project_id) navigate(`/process/${projectData.project_id}`)
    else navigate('/')
  }

  const handleNextStep = (params: { maxRounds?: number }) => {
    addLog(t('log.enterStep3'))
    if (params.maxRounds) {
      addLog(t('log.customRoundsConfig', { rounds: params.maxRounds }))
      navigate(`/simulation/${simulationId}/start?maxRounds=${params.maxRounds}`)
    } else {
      addLog(t('log.useAutoRounds'))
      navigate(`/simulation/${simulationId}/start`)
    }
  }

  const statusText = status === 'error' ? 'Error' : status === 'completed' ? 'Ready' : 'Preparing'

  return (
    <WorkflowLayout
      step={2}
      stepName={stepNames?.[1]}
      statusText={statusText}
      statusVariant={status}
      graphData={graphData}
      graphLoading={graphLoading}
      onRefreshGraph={refreshGraph}
    >
      <Step2EnvSetup
        simulationId={simulationId}
        projectData={projectData}
        systemLogs={systemLogs}
        addLog={addLog}
        onUpdateStatus={setStatus}
        onGoBack={handleGoBack}
        onNextStep={handleNextStep}
      />
    </WorkflowLayout>
  )
}
