import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MessageSquare, Link2, User, ChevronDown, ClipboardCheck } from 'lucide-react'

import { ChatPanel } from '@/components/step5/ChatPanel'
import { SurveyPanel } from '@/components/step5/SurveyPanel'
import { ReportOutlinePanel } from '@/components/step4/ReportOutlinePanel'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { chatWithReport, getReport, getReportSections } from '@/lib/api/report'
import { interviewAgents, getSimulationProfilesRealtime } from '@/lib/api/simulation'
import { cn } from '@/lib/utils'
import type { Profile } from '@/lib/step2-types'
import type { ReportOutline } from '@/lib/step4-types'
import type { ChatMessage, SurveyResult, ToolCall } from '@/lib/step5-types'

interface Step5Props {
  reportId: string
  simulationId: string
  addLog: (msg: string) => void
}

type TargetKey = 'report_agent' | `agent_${number}`

/** 采访接口对单个 Agent 的回复 */
type AgentAnswer = { response?: string; answer?: string }

const initial = (name?: string) => (name || 'A').charAt(0).toUpperCase()

/** 步骤五：深度交互（左：报告正文 / 右：与 ReportAgent / 单个 Agent 对话 + 多 Agent 问卷）。 */
export function Step5Interaction({ reportId, simulationId, addLog }: Step5Props) {
  const { t } = useTranslation()

  const [mode, setMode] = useState<'chat' | 'survey'>('chat')
  const [targetKey, setTargetKey] = useState<TargetKey>('report_agent')
  const [histories, setHistories] = useState<Record<string, ChatMessage[]>>({})
  const [isSending, setIsSending] = useState(false)
  const [profiles, setProfiles] = useState<Profile[]>([])

  // 左侧报告正文
  const [outline, setOutline] = useState<ReportOutline | null>(null)
  const [generatedSections, setGeneratedSections] = useState<Record<number, string>>({})

  // 顶部 Agent 下拉
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // 问卷状态
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [question, setQuestion] = useState('')
  const [isSurveying, setIsSurveying] = useState(false)
  const [surveyResults, setSurveyResults] = useState<SurveyResult[]>([])

  const initedRef = useRef(false)

  const loadProfiles = useCallback(async () => {
    if (!simulationId) return
    try {
      const res = await getSimulationProfilesRealtime(simulationId, 'reddit')
      if (res.success && res.data) {
        setProfiles(res.data.profiles || [])
        addLog(t('log.loadedProfiles', { count: (res.data.profiles || []).length }))
      }
    } catch (err) {
      addLog(t('log.loadProfilesFailed', { error: (err as Error).message }))
    }
  }, [addLog, simulationId, t])

  const loadReport = useCallback(async () => {
    if (!reportId) return
    try {
      addLog(t('log.loadReportData', { id: reportId }))
      const [reportRes, sectionsRes] = await Promise.allSettled([
        getReport(reportId),
        getReportSections(reportId),
      ])

      if (reportRes.status === 'fulfilled' && reportRes.value.success && reportRes.value.data) {
        if (reportRes.value.data.outline) setOutline(reportRes.value.data.outline)
      }

      if (
        sectionsRes.status === 'fulfilled' &&
        sectionsRes.value.success &&
        sectionsRes.value.data
      ) {
        const next: Record<number, string> = {}
        ;(sectionsRes.value.data.sections || []).forEach((section) => {
          if (section.section_index && section.content) {
            next[section.section_index] = section.content
          }
        })
        if (Object.keys(next).length > 0) setGeneratedSections(next)
      }

      addLog(t('log.reportDataLoaded'))
    } catch (err) {
      addLog(t('log.loadReportFailed', { error: (err as Error).message }))
    }
  }, [addLog, reportId, t])

  // 初始化日志仅打印一次
  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    addLog(t('log.step5Init'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 报告随 reportId 加载
  useEffect(() => {
    void loadReport()
  }, [loadReport])

  // 个体档案随 simulationId 加载（simulationId 由父级异步注入，需等其就绪后再拉取）
  useEffect(() => {
    void loadProfiles()
  }, [loadProfiles])

  // 点击外部关闭下拉
  useEffect(() => {
    if (!dropdownOpen) return
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [dropdownOpen])

  const currentMessages = histories[targetKey] || []
  const selectedAgentIndex = targetKey.startsWith('agent_') ? Number(targetKey.slice(6)) : null
  const selectedAgent = selectedAgentIndex !== null ? profiles[selectedAgentIndex] : null

  const append = (key: string, msg: ChatMessage) => {
    setHistories((prev) => ({ ...prev, [key]: [...(prev[key] || []), msg] }))
  }

  const sendMessage = async (text: string) => {
    const key = targetKey
    const prev = histories[key] || []
    append(key, { role: 'user', content: text, timestamp: new Date().toISOString() })
    setIsSending(true)
    try {
      let answer: string
      let toolCalls: ToolCall[] | undefined
      if (key === 'report_agent') {
        addLog(t('log.sendToReportAgent', { message: text.substring(0, 50) }))
        const historyForApi = prev.slice(-10).map((m) => ({ role: m.role, content: m.content }))
        const res = await chatWithReport({
          simulation_id: simulationId,
          message: text,
          chat_history: historyForApi,
        })
        if (!res.success || !res.data) throw new Error(res.error || t('step5.requestFailed'))
        answer = res.data.response || res.data.answer || t('step5.noResponse')
        const rawCalls = res.data.tool_calls
        if (Array.isArray(rawCalls) && rawCalls.length > 0) toolCalls = rawCalls as ToolCall[]
        addLog(t('log.reportAgentReplied'))
      } else {
        const idx = selectedAgentIndex as number
        addLog(
          t('log.sendToAgent', {
            name: selectedAgent?.name || selectedAgent?.username,
            message: text.substring(0, 50),
          }),
        )
        let prompt = text
        if (prev.length > 0) {
          const ctx = prev
            .slice(-6)
            .map(
              (m) =>
                `${m.role === 'user' ? t('step5.askerRole') : t('step5.agentSelfRole')}：${m.content}`,
            )
            .join('\n')
          prompt = t('step5.followupPrompt', { context: ctx, question: text })
        }
        const res = await interviewAgents({
          simulation_id: simulationId,
          interviews: [{ agent_id: idx, prompt }],
        })
        if (!res.success || !res.data) throw new Error(res.error || t('step5.requestFailed'))
        const resultData = res.data.result || res.data
        const dict = (resultData.results || resultData) as Record<string, AgentAnswer>
        const agentResult =
          dict[`reddit_${idx}`] || dict[`twitter_${idx}`] || Object.values(dict)[0]
        answer = (agentResult?.response || agentResult?.answer) ?? t('step5.noResponse')
        addLog(t('log.agentReplied', { name: selectedAgent?.name || selectedAgent?.username }))
      }
      append(key, {
        role: 'assistant',
        content: answer,
        timestamp: new Date().toISOString(),
        toolCalls,
      })
    } catch (err) {
      addLog(t('log.sendFailed', { error: (err as Error).message }))
      append(key, {
        role: 'assistant',
        content: t('step5.errorOccurred', { error: (err as Error).message }),
        timestamp: new Date().toISOString(),
      })
    } finally {
      setIsSending(false)
    }
  }

  const submitSurvey = async () => {
    if (selected.size === 0 || !question.trim()) return
    setIsSurveying(true)
    addLog(t('log.sendSurvey', { count: selected.size }))
    try {
      const interviews = Array.from(selected).map((idx) => ({
        agent_id: idx,
        prompt: question.trim(),
      }))
      const res = await interviewAgents({ simulation_id: simulationId, interviews })
      if (!res.success || !res.data) throw new Error(res.error || t('step5.requestFailed'))
      const resultData = res.data.result || res.data
      const dict = (resultData.results || resultData) as Record<string, AgentAnswer>
      const list: SurveyResult[] = interviews.map(({ agent_id }) => {
        const agent = profiles[agent_id]
        const agentResult = dict[`reddit_${agent_id}`] || dict[`twitter_${agent_id}`]
        return {
          agent_id,
          agent_name: agent?.name || agent?.username || `Agent ${agent_id}`,
          profession: agent?.profession,
          question: question.trim(),
          answer: (agentResult?.response || agentResult?.answer) ?? t('step5.noResponse'),
        }
      })
      setSurveyResults(list)
      addLog(t('log.receivedReplies', { count: list.length }))
    } catch (err) {
      addLog(t('log.surveySendFailed', { error: (err as Error).message }))
    } finally {
      setIsSurveying(false)
    }
  }

  const isReportAgentActive = mode === 'chat' && targetKey === 'report_agent'
  const isAgentActive = mode === 'chat' && targetKey.startsWith('agent_')

  const selectReportAgent = () => {
    setMode('chat')
    setTargetKey('report_agent')
    setDropdownOpen(false)
  }

  const selectAgent = (idx: number) => {
    setMode('chat')
    setTargetKey(`agent_${idx}`)
    setDropdownOpen(false)
    addLog(t('log.selectChatTarget', { name: profiles[idx]?.name || profiles[idx]?.username }))
  }

  return (
    <div className="bg-muted/30 flex h-full overflow-hidden">
      {/* 左侧：报告正文 */}
      <div className="bg-card w-[45%] min-w-[420px] max-w-[680px] flex-shrink-0 overflow-y-auto border-r px-8 py-6 xl:px-10">
        <ReportOutlinePanel
          outline={outline}
          generatedSections={generatedSections}
          currentSectionIndex={null}
        />
      </div>

      {/* 右侧：交互区 */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶部操作栏 */}
        <div className="bg-card flex items-center justify-between gap-4 border-b px-5 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <MessageSquare className="text-foreground/80 h-6 w-6 shrink-0" />
            <div className="flex min-w-0 flex-col">
              <span className="text-sm font-semibold">{t('step5.interactiveTools')}</span>
              <span className="text-muted-foreground font-mono text-[11px]">
                {t('step5.agentsAvailable', { count: profiles.length })}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Report Agent 胶囊 */}
            <Pill active={isReportAgentActive} onClick={selectReportAgent}>
              <Link2 className="h-3.5 w-3.5 opacity-70" />
              <span>{t('step5.chatWithReportAgent')}</span>
            </Pill>

            {/* Agent 下拉 */}
            {profiles.length > 0 && (
              <div className="relative" ref={dropdownRef}>
                <Pill
                  active={isAgentActive}
                  onClick={() => {
                    setDropdownOpen((v) => !v)
                  }}
                  className="w-[200px] justify-between"
                >
                  <span className="flex min-w-0 items-center gap-1.5">
                    <User className="h-3.5 w-3.5 shrink-0 opacity-70" />
                    <span className="truncate">
                      {selectedAgent
                        ? selectedAgent.name || selectedAgent.username
                        : t('step5.chatWithAgent')}
                    </span>
                  </span>
                  <ChevronDown
                    className={cn(
                      'h-3 w-3 shrink-0 opacity-60 transition-transform',
                      dropdownOpen && 'rotate-180',
                    )}
                  />
                </Pill>

                {dropdownOpen && (
                  <div className="bg-card absolute left-1/2 top-[calc(100%+6px)] z-50 max-h-80 w-60 -translate-x-1/2 overflow-y-auto rounded-xl border shadow-lg">
                    <div className="text-muted-foreground border-b px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide">
                      {t('step5.selectChatTarget')}
                    </div>
                    {profiles.map((agent, idx) => (
                      <button
                        key={idx}
                        onClick={() => selectAgent(idx)}
                        className={cn(
                          'hover:bg-accent flex w-full items-center gap-3 border-l-[3px] border-transparent px-4 py-2.5 text-left transition',
                          targetKey === `agent_${idx}` && 'border-brand bg-accent',
                        )}
                      >
                        <Avatar className="h-8 w-8 shrink-0">
                          <AvatarFallback className="bg-brand text-[11px] font-semibold text-white">
                            {initial(agent.name || agent.username)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[13px] font-semibold">
                            {agent.name || agent.username || `Agent ${idx}`}
                          </div>
                          <div className="text-muted-foreground truncate text-[11px]">
                            {agent.profession || t('step2.unknownProfession')}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="bg-border mx-1.5 h-6 w-px" />

            {/* 问卷胶囊 */}
            <Pill
              active={mode === 'survey'}
              onClick={() => {
                setMode('survey')
                setDropdownOpen(false)
              }}
              tone="survey"
            >
              <ClipboardCheck className="h-3.5 w-3.5 opacity-70" />
              <span>{t('step5.sendSurvey')}</span>
            </Pill>
          </div>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-hidden">
          {mode === 'survey' ? (
            <SurveyPanel
              profiles={profiles}
              selected={selected}
              onToggle={(idx) =>
                setSelected((prev) => {
                  const next = new Set(prev)
                  if (next.has(idx)) next.delete(idx)
                  else next.add(idx)
                  return next
                })
              }
              onSelectAll={() => setSelected(new Set(profiles.map((_, i) => i)))}
              onClear={() => setSelected(new Set())}
              question={question}
              setQuestion={setQuestion}
              isSurveying={isSurveying}
              results={surveyResults}
              onSubmit={submitSurvey}
            />
          ) : (
            <ChatPanel
              target={targetKey === 'report_agent' ? 'report_agent' : 'agent'}
              agent={selectedAgent}
              messages={currentMessages}
              isSending={isSending}
              onSend={sendMessage}
            />
          )}
        </div>
      </div>
    </div>
  )
}

/** 操作栏胶囊按钮（默认中性，tone="survey" 为绿色强调）。 */
function Pill({
  active,
  onClick,
  children,
  className,
  tone = 'default',
}: {
  active?: boolean
  onClick: () => void
  children: React.ReactNode
  className?: string
  tone?: 'default' | 'survey'
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 whitespace-nowrap rounded-full border border-transparent px-3.5 py-2 text-xs font-medium transition',
        tone === 'survey'
          ? active
            ? 'bg-emerald-600 text-white shadow-sm'
            : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-400'
          : active
            ? 'bg-foreground text-background shadow-sm'
            : 'bg-muted text-muted-foreground hover:bg-accent hover:text-foreground',
        className,
      )}
    >
      {children}
    </button>
  )
}
