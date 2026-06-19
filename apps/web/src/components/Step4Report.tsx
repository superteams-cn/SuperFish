import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowRight } from 'lucide-react'

import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { ReportOutlinePanel } from '@/components/step4/ReportOutlinePanel'
import { AgentLogTimeline } from '@/components/step4/AgentLogTimeline'
import { getAgentLog, getConsoleLog } from '@/lib/api/report'
import type { SystemLog } from '@/lib/process-types'
import type { AgentLogEntry, ReportOutline } from '@/lib/step4-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

interface Step4Props {
  reportId: string
  systemLogs: SystemLog[]
  addLog: (msg: string) => void
  onUpdateStatus: (s: WorkflowStatus) => void
}

/** 步骤四：报告生成（大纲/章节 markdown + ReportAgent 执行日志 + 控制台 + 进入交互）。 */
export function Step4Report({ reportId, systemLogs, addLog, onUpdateStatus }: Step4Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [agentLogs, setAgentLogs] = useState<AgentLogEntry[]>([])
  const [consoleLogs, setConsoleLogs] = useState<string[]>([])
  const [outline, setOutline] = useState<ReportOutline | null>(null)
  const [currentSectionIndex, setCurrentSectionIndex] = useState<number | null>(null)
  const [generatedSections, setGeneratedSections] = useState<Record<number, string>>({})
  const [isComplete, setIsComplete] = useState(false)

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
      console.warn('Failed to fetch agent log:', err)
    }
  }, [onUpdateStatus, reportId, stopPolling])

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
      console.warn('Failed to fetch console log:', err)
    }
  }, [reportId])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    if (reportId) {
      addLog(`Report Agent initialized: ${reportId}`)
      void fetchAgentLog()
      void fetchConsoleLog()
      agentTimer.current = setInterval(fetchAgentLog, 2000)
      consoleTimer.current = setInterval(fetchConsoleLog, 1500)
    }
    return () => stopPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const consoleAsLogs: SystemLog[] = consoleLogs.map((line) => ({ time: '', msg: line }))

  return (
    <div className="flex h-full flex-col overflow-hidden bg-muted/30">
      <Tabs defaultValue="report" className="flex flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b bg-card px-4 py-2">
          <TabsList>
            <TabsTrigger value="report">{t('step4.predictionReport')}</TabsTrigger>
            <TabsTrigger value="log">Agent Log</TabsTrigger>
            <TabsTrigger value="console">{t('console.title', { defaultValue: '控制台' })}</TabsTrigger>
          </TabsList>
          <Button
            size="sm"
            onClick={() => reportId && navigate(`/interaction/${reportId}`)}
            disabled={!isComplete}
          >
            {t('step4.enterInteraction', { defaultValue: '进入深度互动' })}
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>

        <TabsContent value="report" className="mt-0 flex-1 overflow-y-auto p-6">
          <ReportOutlinePanel
            reportId={reportId}
            outline={outline}
            generatedSections={generatedSections}
            currentSectionIndex={currentSectionIndex}
          />
        </TabsContent>

        <TabsContent value="log" className="mt-0 flex-1 overflow-y-auto p-4">
          {agentLogs.length > 0 ? (
            <AgentLogTimeline logs={agentLogs} />
          ) : (
            <p className="text-sm text-muted-foreground">等待 Agent 执行…</p>
          )}
        </TabsContent>

        <TabsContent value="console" className="mt-0 flex-1 overflow-hidden">
          <div className="h-full overflow-y-auto bg-black p-4 font-mono text-[11px] text-zinc-300">
            {consoleLogs.length === 0 && <span className="text-zinc-600">// 暂无控制台输出</span>}
            {consoleLogs.map((line, idx) => (
              <div key={idx} className="break-all leading-relaxed">
                {line}
              </div>
            ))}
          </div>
        </TabsContent>
      </Tabs>

      {/* 应用级日志（加载/状态） */}
      <SystemLogTerminal logs={systemLogs.length ? systemLogs : consoleAsLogs.slice(-1)} badge={reportId || 'NO_REPORT'} />
    </div>
  )
}
