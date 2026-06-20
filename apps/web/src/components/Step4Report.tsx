import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowRight,
  Download,
  RefreshCw,
  Loader2,
  CheckCircle2,
  Sparkles,
  Code,
  ChevronDown,
} from 'lucide-react'

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
import { cn } from '@/lib/utils'
import type { SystemLog } from '@/lib/process-types'
import type { AgentLogEntry, ReportOutline } from '@/lib/step4-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

const GRADIENT_BTN =
  'bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/40'

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
  const [regenerating, setRegenerating] = useState(false)
  const [backstageOpen, setBackstageOpen] = useState(false)

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

  // 软进度：已完成章节 / 总章节
  const totalSections = outline?.sections?.length ?? 0
  const doneSections = Object.keys(generatedSections).length
  const softProgress = isComplete
    ? 100
    : totalSections > 0
      ? Math.round((doneSections / totalSections) * 100)
      : outline
        ? 8
        : 3

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8">
        <div className="mx-auto max-w-3xl">
          {/* 舞台标题 */}
          <div className="animate-rise-in text-center">
            <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white shadow-lg">
              {isComplete ? (
                <CheckCircle2 className="h-8 w-8" />
              ) : (
                <Loader2 className="h-8 w-8 animate-spin" />
              )}
            </div>
            <h2 className="text-2xl font-semibold tracking-tight">
              {isComplete ? t('step4.cDone') : t('step4.cWriting')}
            </h2>
            <p className="text-muted-foreground mt-2">
              {isComplete ? t('step4.cDoneSub') : t('step4.cWritingSub')}
            </p>
          </div>

          {/* 进展：软进度（生成中） */}
          {!isComplete && (
            <div className="mt-6">
              {totalSections > 0 && (
                <p className="text-muted-foreground mb-2 text-center text-sm">
                  {t('step4.cProgress', { done: doneSections, total: totalSections })}
                </p>
              )}
              <div className="bg-muted h-1.5 overflow-hidden rounded-full">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 transition-all duration-500"
                  style={{ width: `${Math.max(softProgress, 3)}%` }}
                />
              </div>
            </div>
          )}

          {/* 完成 → 深入追问 + 下载 */}
          {isComplete && (
            <div className="animate-rise-in mt-7 flex flex-col items-center gap-3">
              <Button
                className={`${GRADIENT_BTN} h-12 gap-2 rounded-full px-8 text-base`}
                onClick={() => reportId && navigate(`/interaction/${reportId}`)}
              >
                <Sparkles className="h-5 w-5" />
                {t('step4.cNext')}
                <ArrowRight className="h-5 w-5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleDownload}
                disabled={downloading}
                className="text-muted-foreground hover:text-foreground gap-1.5"
              >
                <Download className="h-3.5 w-3.5" />
                {t('step4.downloadReport')}
              </Button>
            </div>
          )}

          {/* 报告本体（章节流式呈现）。不透明「纸」：让长文阅读区脱离动画背景合成，
              避免快速滚动时反复重绘导致的卡顿/白屏。 */}
          <div className="bg-background mt-8 rounded-2xl border p-5 shadow-sm sm:p-7">
            {reportView}
          </div>

          {/* 幕后：工作流进度 / Agent 日志 / 控制台 / 重新生成 */}
          <div className="mt-10">
            <button
              type="button"
              onClick={() => setBackstageOpen((o) => !o)}
              className="text-muted-foreground hover:text-foreground flex w-full items-center justify-between rounded-xl border border-dashed px-4 py-3 text-sm transition-colors"
            >
              <span className="flex items-center gap-2">
                <Code className="h-4 w-4" />
                {t('step4.cBackstage')}
                <span className="text-muted-foreground/70 hidden text-xs sm:inline">
                  · {t('step4.cBackstageHint')}
                </span>
              </span>
              <ChevronDown
                className={cn('h-4 w-4 transition-transform', backstageOpen && 'rotate-180')}
              />
            </button>

            {backstageOpen && (
              <div className="mt-3 space-y-4">
                {simulationId && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRegenerate}
                    disabled={regenerating || (!isComplete && agentLogs.length > 0)}
                    title={t('step4.regenerateReportHint')}
                    className="gap-1.5"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${regenerating ? 'animate-spin' : ''}`} />
                    {t('step4.regenerateReport')}
                  </Button>
                )}
                <div className="bg-background rounded-2xl border p-4">
                  <h3 className="text-muted-foreground mb-2 text-[11px] font-semibold uppercase tracking-wide">
                    {t('step4.workflowProgress')}
                  </h3>
                  {progressView}
                </div>
                <div className="bg-background rounded-2xl border p-4">
                  <h3 className="text-muted-foreground mb-2 text-[11px] font-semibold uppercase tracking-wide">
                    {t('step4.agentLog')}
                  </h3>
                  {logView}
                </div>
                <div className="overflow-hidden rounded-2xl border">
                  <h3 className="text-muted-foreground border-b px-3 py-2 text-[11px] font-semibold uppercase tracking-wide">
                    {t('step4.consoleOutput')}
                  </h3>
                  <div className="h-48">{consoleView}</div>
                </div>
                <SystemLogTerminal
                  logs={systemLogs.length ? systemLogs : consoleAsLogs.slice(-1)}
                  badge={reportId || 'NO_REPORT'}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
