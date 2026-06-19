import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { WorkflowLayout, type WorkflowStatus } from '@/components/WorkflowLayout'
import { Step3Simulation } from '@/components/Step3Simulation'
import { getProject, getGraphData } from '@/lib/api/graph'
import { getSimulation, getSimulationConfig } from '@/lib/api/simulation'
import type { GraphData, ProjectData, SystemLog } from '@/lib/process-types'

export default function SimulationRunPage() {
  const { simulationId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const { t } = useTranslation()
  const stepNames = t('main.stepNames', { returnObjects: true }) as string[]

  const maxRounds = searchParams.get('maxRounds') ? Number(searchParams.get('maxRounds')) : null

  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [systemLogs, setSystemLogs] = useState<SystemLog[]>([])
  const [status, setStatus] = useState<WorkflowStatus>('processing')
  const [minutesPerRound, setMinutesPerRound] = useState(30)
  const initedRef = useRef(false)
  const graphRefreshTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const projectRef = useRef<ProjectData | null>(null)

  const isSimulating = status === 'processing'

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
      return next.length > 200 ? next.slice(next.length - 200) : next
    })
  }, [])

  const loadGraph = useCallback(
    async (graphId: string, silent = false) => {
      if (!silent) setGraphLoading(true)
      try {
        const res = await getGraphData(graphId)
        if (res.success) {
          setGraphData(res.data)
          if (!silent) addLog(t('log.graphDataLoadSuccess'))
        }
      } catch (err) {
        addLog(t('log.graphLoadFailed', { error: (err as Error).message }))
      } finally {
        setGraphLoading(false)
      }
    },
    [addLog, t],
  )

  const refreshGraph = useCallback(
    (silent = false) => {
      if (projectRef.current?.graph_id) void loadGraph(projectRef.current.graph_id, silent)
    },
    [loadGraph],
  )

  const loadSimulationData = useCallback(async () => {
    try {
      addLog(t('log.loadingSimData', { id: simulationId }))
      const simRes = await getSimulation(simulationId)
      if (simRes.success && simRes.data) {
        try {
          const configRes = await getSimulationConfig(simulationId)
          if (configRes.success && configRes.data?.time_config?.minutes_per_round) {
            setMinutesPerRound(configRes.data.time_config.minutes_per_round)
            addLog(t('log.timeConfig', { minutes: configRes.data.time_config.minutes_per_round }))
          }
        } catch {
          addLog(t('log.timeConfigFetchFailed', { minutes: 30 }))
        }
        if (simRes.data.project_id) {
          const projRes = await getProject(simRes.data.project_id)
          if (projRes.success && projRes.data) {
            projectRef.current = projRes.data
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
    addLog(t('log.simRunViewInit'))
    if (maxRounds) addLog(t('log.customRounds', { rounds: maxRounds }))
    void loadSimulationData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 模拟运行时每 30s 静默刷新图谱
  useEffect(() => {
    if (isSimulating && !graphRefreshTimer.current) {
      graphRefreshTimer.current = setInterval(() => refreshGraph(true), 30000)
    } else if (!isSimulating && graphRefreshTimer.current) {
      clearInterval(graphRefreshTimer.current)
      graphRefreshTimer.current = null
    }
    return () => {
      if (graphRefreshTimer.current) {
        clearInterval(graphRefreshTimer.current)
        graphRefreshTimer.current = null
      }
    }
  }, [isSimulating, refreshGraph])

  const statusText = status === 'error' ? 'Error' : status === 'completed' ? 'Completed' : 'Running'

  return (
    <WorkflowLayout
      step={3}
      stepName={stepNames?.[2]}
      statusText={statusText}
      statusVariant={status}
      graphData={graphData}
      graphLoading={graphLoading}
      onRefreshGraph={() => refreshGraph(false)}
    >
      <Step3Simulation
        simulationId={simulationId}
        maxRounds={maxRounds}
        minutesPerRound={minutesPerRound}
        systemLogs={systemLogs}
        addLog={addLog}
        onUpdateStatus={setStatus}
      />
    </WorkflowLayout>
  )
}
