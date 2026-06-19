import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bot, Users, ClipboardList } from 'lucide-react'

import { ChatPanel } from '@/components/step5/ChatPanel'
import { SurveyPanel } from '@/components/step5/SurveyPanel'
import { chatWithReport, getAgentLog, getReport } from '@/lib/api/report'
import { interviewAgents, getSimulationProfilesRealtime } from '@/lib/api/simulation'
import { cn } from '@/lib/utils'
import type { Profile } from '@/lib/step2-types'
import type { ChatMessage, SurveyResult } from '@/lib/step5-types'

interface Step5Props {
  reportId: string
  simulationId: string
  addLog: (msg: string) => void
}

type TargetKey = 'report_agent' | `agent_${number}`

/** 步骤五：深度交互（与 ReportAgent / 单个 Agent 对话 + 多 Agent 问卷）。 */
export function Step5Interaction({ reportId, simulationId, addLog }: Step5Props) {
  const { t } = useTranslation()

  const [mode, setMode] = useState<'chat' | 'survey'>('chat')
  const [targetKey, setTargetKey] = useState<TargetKey>('report_agent')
  const [histories, setHistories] = useState<Record<string, ChatMessage[]>>({})
  const [isSending, setIsSending] = useState(false)
  const [profiles, setProfiles] = useState<Profile[]>([])

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
      const reportRes = await getReport(reportId)
      if (reportRes.success && reportRes.data) {
        // 预拉一次 agent log（用于确认报告就绪）
        await getAgentLog(reportId, 0)
        addLog(t('log.reportDataLoaded'))
      }
    } catch (err) {
      addLog(t('log.loadReportFailed', { error: (err as Error).message }))
    }
  }, [addLog, reportId, t])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    addLog(t('log.step5Init'))
    void loadReport()
    void loadProfiles()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
        addLog(t('log.reportAgentReplied'))
      } else {
        const idx = selectedAgentIndex as number
        addLog(t('log.sendToAgent', { name: selectedAgent?.username, message: text.substring(0, 50) }))
        let prompt = text
        if (prev.length > 0) {
          const ctx = prev
            .slice(-6)
            .map((m) => `${m.role === 'user' ? '提问者' : '你'}：${m.content}`)
            .join('\n')
          prompt = `以下是我们之前的对话：\n${ctx}\n\n现在我的新问题是：${text}`
        }
        const res = await interviewAgents({
          simulation_id: simulationId,
          interviews: [{ agent_id: idx, prompt }],
        })
        if (!res.success || !res.data) throw new Error(res.error || t('step5.requestFailed'))
        const resultData = res.data.result || res.data
        const dict = resultData.results || resultData
        const agentResult = dict[`reddit_${idx}`] || dict[`twitter_${idx}`] || Object.values(dict)[0]
        answer = (agentResult?.response || agentResult?.answer) ?? t('step5.noResponse')
        addLog(t('log.agentReplied', { name: selectedAgent?.username }))
      }
      append(key, { role: 'assistant', content: answer, timestamp: new Date().toISOString() })
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
      const interviews = Array.from(selected).map((idx) => ({ agent_id: idx, prompt: question.trim() }))
      const res = await interviewAgents({ simulation_id: simulationId, interviews })
      if (!res.success || !res.data) throw new Error(res.error || t('step5.requestFailed'))
      const resultData = res.data.result || res.data
      const dict = resultData.results || resultData
      const list: SurveyResult[] = interviews.map(({ agent_id }) => {
        const agent = profiles[agent_id]
        const agentResult = dict[`reddit_${agent_id}`] || dict[`twitter_${agent_id}`]
        return {
          agent_id,
          agent_name: agent?.username || `Agent ${agent_id}`,
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

  return (
    <div className="flex h-full overflow-hidden bg-muted/30">
      {/* 左侧目标选择 */}
      <div className="flex w-56 flex-shrink-0 flex-col gap-1 overflow-y-auto border-r bg-card p-3">
        <SidebarItem
          icon={<Bot className="h-4 w-4" />}
          label={t('step5.chatWithReportAgent')}
          active={mode === 'chat' && targetKey === 'report_agent'}
          onClick={() => {
            setMode('chat')
            setTargetKey('report_agent')
          }}
        />
        <div className="mt-2 px-2 text-[10px] font-semibold uppercase text-muted-foreground">
          <Users className="mr-1 inline h-3 w-3" />
          Agents
        </div>
        {profiles.map((p, idx) => (
          <SidebarItem
            key={idx}
            label={p.username || `Agent ${idx}`}
            sub={p.profession}
            active={mode === 'chat' && targetKey === `agent_${idx}`}
            onClick={() => {
              setMode('chat')
              setTargetKey(`agent_${idx}`)
            }}
          />
        ))}
        <SidebarItem
          icon={<ClipboardList className="h-4 w-4" />}
          label={t('step5.survey', { defaultValue: '问卷调查' })}
          active={mode === 'survey'}
          onClick={() => setMode('survey')}
          className="mt-2"
        />
      </div>

      {/* 右侧主区 */}
      <div className="flex-1 overflow-hidden">
        {mode === 'survey' ? (
          <SurveyPanel
            profiles={profiles}
            selected={selected}
            onToggle={(idx) =>
              setSelected((prev) => {
                const next = new Set(prev)
                next.has(idx) ? next.delete(idx) : next.add(idx)
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
            title={
              targetKey === 'report_agent'
                ? t('step5.chatWithReportAgent')
                : selectedAgent?.username || 'Agent'
            }
            subtitle={targetKey === 'report_agent' ? reportId : selectedAgent?.profession}
            messages={currentMessages}
            isSending={isSending}
            onSend={sendMessage}
          />
        )}
      </div>
    </div>
  )
}

function SidebarItem({
  icon,
  label,
  sub,
  active,
  onClick,
  className,
}: {
  icon?: React.ReactNode
  label: string
  sub?: string
  active?: boolean
  onClick: () => void
  className?: string
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition',
        active ? 'bg-[#FF5722] text-white' : 'hover:bg-accent',
        className,
      )}
    >
      {icon}
      <span className="min-w-0 flex-1">
        <span className="block truncate">{label}</span>
        {sub && (
          <span className={cn('block truncate text-[10px]', active ? 'text-white/70' : 'text-muted-foreground')}>
            {sub}
          </span>
        )}
      </span>
    </button>
  )
}
