import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight, Download, RefreshCw } from 'lucide-react'

import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { ReportOutlinePanel } from '@/components/step4/ReportOutlinePanel'
import { AgentLogTimeline } from '@/components/step4/AgentLogTimeline'
import { WorkflowProgressPanel } from '@/components/step4/WorkflowProgressPanel'
import { ConsoleLogView } from '@/components/step4/ConsoleLogView'
import {
  getAgentLog,
  getConsoleLog,
  downloadReport,
  generateReport,
  getReport,
  getReportProgress,
  getReportSections,
} from '@/lib/api/report'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import type { SystemLog } from '@/lib/process-types'
import type { AgentLogEntry, ReportOutline } from '@/lib/step4-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

interface Step4Props {
  reportId: string
  /** 所属模拟 id，用于重新生成报告 */
  simulationId?: string
  systemLogs: SystemLog[]
  addLog: (msg: string) => void
  onUpdateStatus: (s: WorkflowStatus) => void
}

/**
 * 步骤四：报告生成。
 * 宽屏：左报告 / 右(进度 + Agent 日志 + 控制台) 双面板可同时观察；
 * 窄屏：降级为 Tab 串行切换。
 */
export function Step4Report({
  reportId,
  simulationId,
  systemLogs,
  addLog,
  onUpdateStatus,
}: Step4Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isNarrow = useMediaQuery('(max-width: 1024px)')
  const [regenerating, setRegenerating] = useState(false)

  const [agentLogs, setAgentLogs] = useState<AgentLogEntry[]>([])
  const [consoleLogs, setConsoleLogs] = useState<string[]>([])
  const [outline, setOutline] = useState<ReportOutline | null>(null)
  const [currentSectionIndex, setCurrentSectionIndex] = useState<number | null>(null)
  const [generatedSections, setGeneratedSections] = useState<Record<number, string>>({})
  const [isComplete, setIsComplete] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const agentLine = useRef(0)
  const consoleLine = useRef(0)
  const agentTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const consoleTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const snapshotTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const fetchingSnapshot = useRef(false)
  const outlineRef = useRef<ReportOutline | null>(null)

  const stopPolling = useCallback(() => {
    if (agentTimer.current) clearInterval(agentTimer.current)
    if (consoleTimer.current) clearInterval(consoleTimer.current)
    if (snapshotTimer.current) clearInterval(snapshotTimer.current)
    agentTimer.current = null
    consoleTimer.current = null
    snapshotTimer.current = null
  }, [])

  const mergeSectionContent = useCallback((sectionIndex: number | undefined, content: unknown) => {
    if (!sectionIndex || typeof content !== 'string' || !content.trim()) return
    setGeneratedSections((prev) => {
      if (prev[sectionIndex] === content) return prev
      return { ...prev, [sectionIndex]: content }
    })
  }, [])

  const applyOutline = useCallback((nextOutline: ReportOutline) => {
    outlineRef.current = nextOutline
    setOutline(nextOutline)
  }, [])

  const updateCurrentSectionFromTitle = useCallback((title?: string | null) => {
    if (!title) {
      setCurrentSectionIndex(null)
      return
    }
    const idx = outlineRef.current?.sections?.findIndex((section) => section.title === title) ?? -1
    setCurrentSectionIndex(idx >= 0 ? idx + 1 : null)
  }, [])

  const fetchReportSnapshot = useCallback(async () => {
    if (!reportId || fetchingSnapshot.current) return
    fetchingSnapshot.current = true
    try {
      const [reportRes, sectionsRes, progressRes] = await Promise.allSettled([
        getReport(reportId),
        getReportSections(reportId),
        getReportProgress(reportId),
      ])

      if (reportRes.status === 'fulfilled' && reportRes.value.success && reportRes.value.data) {
        const report = reportRes.value.data
        if (report.outline) applyOutline(report.outline)
        if (report.status === 'completed') {
          setIsComplete(true)
          setCurrentSectionIndex(null)
          onUpdateStatus('completed')
        }
      }

      if (
        sectionsRes.status === 'fulfilled' &&
        sectionsRes.value.success &&
        sectionsRes.value.data
      ) {
        const snapshotSections = sectionsRes.value.data.sections || []
        setGeneratedSections((prev) => {
          const next = { ...prev }
          let changed = false
          snapshotSections.forEach((section) => {
            if (!section.section_index || !section.content) return
            if (next[section.section_index] !== section.content) {
              next[section.section_index] = section.content
              changed = true
            }
          })
          return changed ? next : prev
        })
        if (sectionsRes.value.data.is_complete) {
          setIsComplete(true)
          setCurrentSectionIndex(null)
          onUpdateStatus('completed')
        }
      }

      if (
        progressRes.status === 'fulfilled' &&
        progressRes.value.success &&
        progressRes.value.data
      ) {
        const progress = progressRes.value.data
        if (progress.stage === 'completed' || progress.status === 'completed') {
          setIsComplete(true)
          setCurrentSectionIndex(null)
          onUpdateStatus('completed')
        } else if (progress.current_section) {
          updateCurrentSectionFromTitle(progress.current_section)
        }
      }
    } catch (err) {
      addLog(t('log.loadException', { error: (err as Error).message }))
    } finally {
      fetchingSnapshot.current = false
    }
  }, [addLog, applyOutline, onUpdateStatus, reportId, t, updateCurrentSectionFromTitle])

  const fetchAgentLog = useCallback(async () => {
    if (!reportId) return
    try {
      const res = await getAgentLog(reportId, agentLine.current)
      if (!res.success || !res.data) return
      const newLogs: AgentLogEntry[] = res.data.logs || []
      if (!newLogs.length) return

      setAgentLogs((prev) => [...prev, ...newLogs])
      newLogs.forEach((log) => {
        if (log.action === 'planning_complete' && log.details?.outline) {
          applyOutline(log.details.outline)
        }
        if (log.action === 'section_start') {
          setCurrentSectionIndex(log.section_index ?? null)
        }
        if (log.action === 'section_content') {
          mergeSectionContent(log.section_index, log.details?.content)
        }
        if (log.action === 'section_complete' && log.details?.content && log.section_index) {
          mergeSectionContent(log.section_index, log.details.content)
          setCurrentSectionIndex(null)
        }
        if (log.action === 'report_complete') {
          setIsComplete(true)
          setCurrentSectionIndex(null)
          onUpdateStatus('completed')
          stopPolling()
        }
      })
      agentLine.current = res.data.total_lines ?? res.data.from_line + newLogs.length
    } catch (err) {
      addLog(t('log.fetchAgentLogFailed', { error: (err as Error).message }))
    }
  }, [addLog, applyOutline, mergeSectionContent, onUpdateStatus, reportId, stopPolling, t])

  const fetchConsoleLog = useCallback(async () => {
    if (!reportId) return
    try {
      const res = await getConsoleLog(reportId, consoleLine.current)
      if (!res.success || !res.data) return
      const newLogs: string[] = res.data.logs || []
      if (!newLogs.length) return
      setConsoleLogs((prev) => [...prev, ...newLogs])
      consoleLine.current = res.data.total_lines ?? res.data.from_line + newLogs.length
    } catch (err) {
      addLog(t('log.fetchConsoleLogFailed', { error: (err as Error).message }))
    }
  }, [addLog, reportId, t])

  useEffect(() => {
    stopPolling()
    setAgentLogs([])
    setConsoleLogs([])
    setOutline(null)
    outlineRef.current = null
    setCurrentSectionIndex(null)
    setGeneratedSections({})
    setIsComplete(false)
    agentLine.current = 0
    consoleLine.current = 0
    fetchingSnapshot.current = false

    if (reportId) {
      addLog(t('log.reportAgentInitialized', { reportId }))
      void fetchReportSnapshot()
      void fetchAgentLog()
      void fetchConsoleLog()
      snapshotTimer.current = setInterval(fetchReportSnapshot, 2500)
      agentTimer.current = setInterval(fetchAgentLog, 2000)
      consoleTimer.current = setInterval(fetchConsoleLog, 1500)
    }
    return () => stopPolling()
  }, [addLog, fetchAgentLog, fetchConsoleLog, fetchReportSnapshot, reportId, stopPolling, t])

  const handleDownload = useCallback(async () => {
    if (!reportId || downloading) return
    setDownloading(true)
    try {
      const blob = await downloadReport(reportId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${reportId}.md`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      addLog(t('log.reportDownloaded', { reportId }))
    } catch (err) {
      addLog(t('log.reportDownloadFailed', { error: (err as Error).message }))
    } finally {
      setDownloading(false)
    }
  }, [addLog, downloading, reportId, t])

  const consoleAsLogs: SystemLog[] = consoleLogs.map((line) => ({ time: '', msg: line }))

  /* ── 可复用片段 ─────────────────────────────────────── */
  const reportView = (
    <ReportOutlinePanel
      reportId={reportId}
      outline={outline}
      generatedSections={generatedSections}
      currentSectionIndex={currentSectionIndex}
    />
  )

  const progressView = (
    <WorkflowProgressPanel
      logs={agentLogs}
      outline={outline}
      generatedSections={generatedSections}
      currentSectionIndex={currentSectionIndex}
      isComplete={isComplete}
    />
  )

  const logView =
    agentLogs.length > 0 ? (
      <AgentLogTimeline logs={agentLogs} />
    ) : (
      <p className="text-muted-foreground text-sm">{t('step4.waitingForAgentExecution')}</p>
    )

  const consoleView = (
    <ConsoleLogView logs={consoleLogs} emptyText={t('step4.emptyConsoleOutput')} />
  )

  const handleRegenerate = useCallback(async () => {
    if (!simulationId || regenerating) return
    setRegenerating(true)
    stopPolling()
    // 重置展示状态，准备重新生成
    setAgentLogs([])
    setConsoleLogs([])
    outlineRef.current = null
    setOutline(null)
    setCurrentSectionIndex(null)
    setGeneratedSections({})
    setIsComplete(false)
    agentLine.current = 0
    consoleLine.current = 0
    fetchingSnapshot.current = false
    onUpdateStatus('processing')
    try {
      const res = await generateReport({ simulation_id: simulationId, force_regenerate: true })
      if (res.success && res.data) {
        addLog(t('log.regeneratingReport'))
        const newId = res.data.report_id
        if (newId && newId !== reportId) {
          navigate(`/report/${newId}`, { replace: true })
          return
        }
        void fetchReportSnapshot()
        snapshotTimer.current = setInterval(fetchReportSnapshot, 2500)
        agentTimer.current = setInterval(fetchAgentLog, 2000)
        consoleTimer.current = setInterval(fetchConsoleLog, 1500)
      } else {
        addLog(t('log.regenerateReportFailed', { error: res.error || t('common.unknownError') }))
        onUpdateStatus('error')
      }
    } catch (err) {
      addLog(t('log.regenerateReportFailed', { error: (err as Error).message }))
      onUpdateStatus('error')
    } finally {
      setRegenerating(false)
    }
  }, [
    simulationId,
    regenerating,
    stopPolling,
    onUpdateStatus,
    addLog,
    t,
    reportId,
    navigate,
    fetchReportSnapshot,
    fetchAgentLog,
    fetchConsoleLog,
  ])

  const actions = (
    <div className="flex items-center gap-2">
      {simulationId && (
        <Button
          size="sm"
          variant="ghost"
          onClick={handleRegenerate}
          disabled={regenerating || (!isComplete && agentLogs.length > 0)}
          title={t('step4.regenerateReportHint')}
          className="text-muted-foreground hover:text-foreground"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${regenerating ? 'animate-spin' : ''}`} />
          {t('step4.regenerateReport')}
        </Button>
      )}
      <Button
        size="sm"
        variant="outline"
        onClick={handleDownload}
        disabled={!isComplete || downloading}
      >
        <Download className="h-3.5 w-3.5" />
        {t('step4.downloadReport')}
      </Button>
      <Button
        size="sm"
        onClick={() => reportId && navigate(`/interaction/${reportId}`)}
        disabled={!isComplete}
      >
        {t('step4.enterInteraction')}
        <ArrowRight className="h-3.5 w-3.5" />
      </Button>
    </div>
  )

  return (
    <div className="bg-muted/30 flex h-full flex-col overflow-hidden">
      {isNarrow ? (
        /* 窄屏：Tab 串行切换 */
        <Tabs defaultValue="report" className="flex flex-1 flex-col overflow-hidden">
          <div className="bg-card flex items-center justify-between border-b px-4 py-2">
            <TabsList>
              <TabsTrigger value="report">{t('step4.predictionReport')}</TabsTrigger>
              <TabsTrigger value="progress">{t('step4.workflowProgress')}</TabsTrigger>
              <TabsTrigger value="log">{t('step4.agentLog')}</TabsTrigger>
              <TabsTrigger value="console">{t('step4.consoleOutput')}</TabsTrigger>
            </TabsList>
            {actions}
          </div>
          <TabsContent value="report" className="mt-0 flex-1 overflow-y-auto p-6">
            {reportView}
          </TabsContent>
          <TabsContent value="progress" className="mt-0 flex-1 overflow-y-auto p-4">
            {progressView}
          </TabsContent>
          <TabsContent value="log" className="mt-0 flex-1 overflow-y-auto p-4">
            {logView}
          </TabsContent>
          <TabsContent value="console" className="mt-0 flex-1 overflow-hidden">
            {consoleView}
          </TabsContent>
        </Tabs>
      ) : (
        /* 宽屏：左报告 / 右(进度 + 日志 + 控制台) 并行双面板 */
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="bg-card flex items-center justify-end border-b px-4 py-2">{actions}</div>
          <div className="flex flex-1 overflow-hidden">
            {/* 左：报告章节流 */}
            <div className="flex-1 overflow-y-auto px-8 py-6 xl:px-12">{reportView}</div>

            {/* 右：进度 + 日志 + 控制台（纵向同时可见） */}
            <div className="bg-card flex w-[32%] min-w-[340px] max-w-[460px] flex-col overflow-hidden border-l">
              <div className="border-b p-3">
                <h3 className="text-muted-foreground mb-2 text-[11px] font-semibold uppercase tracking-wide">
                  {t('step4.workflowProgress')}
                </h3>
                {progressView}
              </div>
              <div className="flex min-h-0 flex-1 flex-col">
                <h3 className="text-muted-foreground border-b px-3 py-2 text-[11px] font-semibold uppercase tracking-wide">
                  {t('step4.agentLog')}
                </h3>
                <div className="flex-1 overflow-y-auto p-3">{logView}</div>
              </div>
              <div className="flex h-[30%] min-h-[120px] flex-col border-t">
                <h3 className="text-muted-foreground border-b px-3 py-2 text-[11px] font-semibold uppercase tracking-wide">
                  {t('step4.consoleOutput')}
                </h3>
                <div className="min-h-0 flex-1">{consoleView}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 应用级日志（加载/状态） */}
      <SystemLogTerminal
        logs={systemLogs.length ? systemLogs : consoleAsLogs.slice(-1)}
        badge={reportId || 'NO_REPORT'}
      />
    </div>
  )
}
