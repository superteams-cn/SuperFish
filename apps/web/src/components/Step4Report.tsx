import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight, Download } from 'lucide-react'

import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { ReportOutlinePanel } from '@/components/step4/ReportOutlinePanel'
import { AgentLogTimeline } from '@/components/step4/AgentLogTimeline'
import { WorkflowProgressPanel } from '@/components/step4/WorkflowProgressPanel'
import { getAgentLog, getConsoleLog, downloadReport } from '@/lib/api/report'
import type { SystemLog } from '@/lib/process-types'
import type { AgentLogEntry, ReportOutline } from '@/lib/step4-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

interface Step4Props {
  reportId: string
  systemLogs: SystemLog[]
  addLog: (msg: string) => void
  onUpdateStatus: (s: WorkflowStatus) => void
}

/** 监听媒体查询（窄屏降级判断）。 */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  )
  useEffect(() => {
    const mql = window.matchMedia(query)
    const handler = () => setMatches(mql.matches)
    handler()
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [query])
  return matches
}

/**
 * 步骤四：报告生成。
 * 宽屏：左报告 / 右(进度 + Agent 日志 + 控制台) 双面板可同时观察；
 * 窄屏：降级为 Tab 串行切换。
 */
export function Step4Report({ reportId, systemLogs, addLog, onUpdateStatus }: Step4Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isNarrow = useMediaQuery('(max-width: 1024px)')

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
  const initedRef = useRef(false)

  const stopPolling = useCallback(() => {
    if (agentTimer.current) clearInterval(agentTimer.current)
    if (consoleTimer.current) clearInterval(consoleTimer.current)
    agentTimer.current = null
    consoleTimer.current = null
  }, [])

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
          setOutline(log.details.outline)
        }
        if (log.action === 'section_start') {
          setCurrentSectionIndex(log.section_index ?? null)
        }
        if (log.action === 'section_complete' && log.details?.content && log.section_index) {
          const sIdx = log.section_index
          const content = log.details.content
          setGeneratedSections((prev) => ({ ...prev, [sIdx]: content }))
          setCurrentSectionIndex(null)
        }
        if (log.action === 'report_complete') {
          setIsComplete(true)
          setCurrentSectionIndex(null)
          onUpdateStatus('completed')
          stopPolling()
        }
      })
      agentLine.current = res.data.from_line + newLogs.length
    } catch (err) {
      addLog(t('log.fetchAgentLogFailed', { error: (err as Error).message }))
    }
  }, [addLog, onUpdateStatus, reportId, stopPolling, t])

  const fetchConsoleLog = useCallback(async () => {
    if (!reportId) return
    try {
      const res = await getConsoleLog(reportId, consoleLine.current)
      if (!res.success || !res.data) return
      const newLogs: string[] = res.data.logs || []
      if (!newLogs.length) return
      setConsoleLogs((prev) => [...prev, ...newLogs])
      consoleLine.current = res.data.from_line + newLogs.length
    } catch (err) {
      addLog(t('log.fetchConsoleLogFailed', { error: (err as Error).message }))
    }
  }, [addLog, reportId, t])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    if (reportId) {
      addLog(t('log.reportAgentInitialized', { reportId }))
      void fetchAgentLog()
      void fetchConsoleLog()
      agentTimer.current = setInterval(fetchAgentLog, 2000)
      consoleTimer.current = setInterval(fetchConsoleLog, 1500)
    }
    return () => stopPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
    <div className="h-full overflow-y-auto bg-black p-4 font-mono text-[11px] text-zinc-300">
      {consoleLogs.length === 0 && (
        <span className="text-zinc-600">{t('step4.emptyConsoleOutput')}</span>
      )}
      {consoleLogs.map((line, idx) => (
        <div key={idx} className="break-all leading-relaxed">
          {line}
        </div>
      ))}
    </div>
  )

  const actions = (
    <div className="flex items-center gap-2">
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
            <div className="flex-1 overflow-y-auto p-6">{reportView}</div>

            {/* 右：进度 + 日志 + 控制台（纵向同时可见） */}
            <div className="bg-card flex w-[40%] min-w-[360px] max-w-[520px] flex-col overflow-hidden border-l">
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
