import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { WorkflowLayout, type WorkflowStatus } from '@/components/WorkflowLayout'
import { Step4Report } from '@/components/Step4Report'
import { getProject, getGraphData } from '@/lib/api/graph'
import { getSimulation } from '@/lib/api/simulation'
import { getReport } from '@/lib/api/report'
import type { GraphData, ProjectData, SystemLog } from '@/lib/process-types'

export default function ReportPage() {
  const { reportId = '' } = useParams()
  const { t } = useTranslation()
  const stepNames = t('main.stepNames', { returnObjects: true }) as string[]

  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [systemLogs, setSystemLogs] = useState<SystemLog[]>([])
  const [status, setStatus] = useState<WorkflowStatus>('processing')
  const projectRef = useRef<ProjectData | null>(null)
  const initedRef = useRef(false)

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

  const loadReportData = useCallback(async () => {
    try {
      addLog(t('log.loadReportData', { id: reportId }))
      const reportRes = await getReport(reportId)
      if (reportRes.success && reportRes.data) {
        const simId = reportRes.data.simulation_id
        if (simId) {
          const simRes = await getSimulation(simId)
          if (simRes.success && simRes.data?.project_id) {
            const projRes = await getProject(simRes.data.project_id)
            if (projRes.success && projRes.data) {
              projectRef.current = projRes.data
              addLog(t('log.projectLoadSuccess', { id: projRes.data.project_id }))
              if (projRes.data.graph_id) await loadGraph(projRes.data.graph_id)
            }
          }
        }
      } else {
        addLog(t('log.getReportInfoFailed', { error: reportRes.error || t('common.unknownError') }))
      }
    } catch (err) {
      addLog(t('log.loadException', { error: (err as Error).message }))
    }
  }, [addLog, loadGraph, reportId, t])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    addLog(t('log.reportViewInit'))
    void loadReportData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshGraph = () => {
    if (projectRef.current?.graph_id) void loadGraph(projectRef.current.graph_id)
  }

  const statusText =
    status === 'error' ? 'Error' : status === 'completed' ? 'Completed' : 'Generating'

  return (
    <WorkflowLayout
      step={4}
      stepName={stepNames?.[3]}
      statusText={statusText}
      statusVariant={status}
      graphData={graphData}
      graphLoading={graphLoading}
      onRefreshGraph={refreshGraph}
      initialViewMode="workbench"
    >
      <Step4Report
        reportId={reportId}
        systemLogs={systemLogs}
        addLog={addLog}
        onUpdateStatus={setStatus}
      />
    </WorkflowLayout>
  )
}
