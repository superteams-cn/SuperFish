import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { WorkflowLayout } from '@/components/WorkflowLayout'
import { Step5Interaction } from '@/components/Step5Interaction'
import { getProject, getGraphData } from '@/lib/api/graph'
import { getSimulation } from '@/lib/api/simulation'
import { getReport } from '@/lib/api/report'
import type { GraphData, ProjectData } from '@/lib/process-types'

export default function InteractionPage() {
  const { reportId = '' } = useParams()
  const { t } = useTranslation()
  const stepNames = t('main.stepNames', { returnObjects: true }) as string[]

  const [simulationId, setSimulationId] = useState('')
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const projectRef = useRef<ProjectData | null>(null)
  const initedRef = useRef(false)

  // 交互页的应用级日志仅打印到控制台即可（不展示终端）
  const addLog = useCallback((msg: string) => console.info('[interaction]', msg), [])

  const loadGraph = useCallback(async (graphId: string) => {
    setGraphLoading(true)
    try {
      const res = await getGraphData(graphId)
      if (res.success) setGraphData(res.data)
    } finally {
      setGraphLoading(false)
    }
  }, [])

  const loadData = useCallback(async () => {
    const reportRes = await getReport(reportId)
    if (reportRes.success && reportRes.data?.simulation_id) {
      const simId = reportRes.data.simulation_id
      setSimulationId(simId)
      const simRes = await getSimulation(simId)
      if (simRes.success && simRes.data?.project_id) {
        const projRes = await getProject(simRes.data.project_id)
        if (projRes.success && projRes.data) {
          projectRef.current = projRes.data
          if (projRes.data.graph_id) await loadGraph(projRes.data.graph_id)
        }
      }
    }
  }, [loadGraph, reportId])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    void loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshGraph = () => {
    if (projectRef.current?.graph_id) void loadGraph(projectRef.current.graph_id)
  }

  return (
    <WorkflowLayout
      step={5}
      stepName={stepNames?.[4]}
      statusText="Ready"
      statusVariant="completed"
      graphData={graphData}
      graphLoading={graphLoading}
      onRefreshGraph={refreshGraph}
      initialViewMode="workbench"
    >
      <Step5Interaction reportId={reportId} simulationId={simulationId} addLog={addLog} />
    </WorkflowLayout>
  )
}
