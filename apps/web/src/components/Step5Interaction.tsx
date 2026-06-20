import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Sparkles, User, Users, ArrowLeft, Loader2 } from 'lucide-react'

import { ChatPanel } from '@/components/step5/ChatPanel'
import { SurveyPanel } from '@/components/step5/SurveyPanel'
import { ReportOutlinePanel } from '@/components/step4/ReportOutlinePanel'
import { Logo } from '@/components/common/Logo'
import { chatWithReport, getReport, getReportSections } from '@/lib/api/report'
import {
  interviewAgents,
  getSimulationProfilesRealtime,
  ensureEnv,
  getEnvStatus,
} from '@/lib/api/simulation'
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
/** 追问对象：问 SuperFish / 问一个人 / 问一群人 */
type Tab = 'super' | 'one' | 'crowd'

/** 采访接口对单个 Agent 的回复 */
type AgentAnswer = { response?: string; answer?: string }

const initial = (name?: string) => (name || 'A').charAt(0).toUpperCase()

/** 步骤五：深入追问（左：结论报告 / 右：问 SuperFish · 问一个人 · 问一群人）。 */
export function Step5Interaction({ reportId, simulationId, addLog }: Step5Props) {
  const { t } = useTranslation()

  const [tab, setTab] = useState<Tab>('super')
  const [targetKey, setTargetKey] = useState<TargetKey>('report_agent')
  const [histories, setHistories] = useState<Record<string, ChatMessage[]>>({})
  const [isSending, setIsSending] = useState(false)
  const [profiles, setProfiles] = useState<Profile[]>([])

  // 左侧报告正文
  const [outline, setOutline] = useState<ReportOutline | null>(null)
  const [generatedSections, setGeneratedSections] = useState<Record<number, string>>({})

  // 问卷状态
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [question, setQuestion] = useState('')
  const [isSurveying, setIsSurveying] = useState(false)
  const [surveyResults, setSurveyResults] = useState<SurveyResult[]>([])
  // 采访需要模拟环境存活；推演结束后环境可能已回收，发起采访前按需唤醒（恢复记忆）
  const [wakingEnv, setWakingEnv] = useState(false)

  const initedRef = useRef(false)

  // 确保环境就绪：已活直接 true；否则触发唤醒并轮询至 alive（最多 ~90s）
  const ensureEnvReady = useCallback(async (): Promise<boolean> => {
    try {
      const res = await ensureEnv({ simulation_id: simulationId })
      if (!res.success) return false
      if (res.data?.status === 'alive') return true
      setWakingEnv(true)
      const deadline = Date.now() + 90_000
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2000))
        const s = await getEnvStatus({ simulation_id: simulationId })
        if (s.success && s.data?.env_alive) return true
      }
      return false
    } catch {
      return false
    } finally {
      setWakingEnv(false)
    }
  }, [simulationId])

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
        // 采访前确保环境就绪（必要时唤醒并恢复记忆）；唤醒失败则走人话兜底
        const ready = await ensureEnvReady()
        if (!ready) throw new Error('env-not-ready')
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
      // 直接追问某个人需要模拟环境仍在运行；推演结束后环境多半已回收 → 人话引导改问 SuperFish
      const friendly =
        key !== 'report_agent'
          ? t('step5.cAgentUnavailable')
          : t('step5.errorOccurred', { error: (err as Error).message })
      append(key, {
        role: 'assistant',
        content: friendly,
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
      // 群访同样需要环境就绪，必要时先唤醒
      const ready = await ensureEnvReady()
      if (!ready) {
        addLog(t('step5.cAgentUnavailable'))
        return
      }
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

  /* ── 追问对象切换 ─────────────────────────────────────── */
  const selectSuper = () => {
    setTab('super')
    setTargetKey('report_agent')
  }
  const selectOne = () => setTab('one')
  const selectCrowd = () => setTab('crowd')

  const pickAgent = (idx: number) => {
    setTargetKey(`agent_${idx}`)
    addLog(t('log.selectChatTarget', { name: profiles[idx]?.name || profiles[idx]?.username }))
  }
  const backToPicker = () => setTargetKey('report_agent')

  return (
    <div className="flex h-full overflow-hidden">
      {/* 左侧：结论报告（不透明「纸」，可对照追问；长滚动不卡） */}
      <div className="bg-background w-[44%] min-w-[400px] max-w-[660px] flex-shrink-0 overflow-y-auto border-r px-8 py-6 xl:px-10">
        <ReportOutlinePanel
          outline={outline}
          generatedSections={generatedSections}
          currentSectionIndex={null}
        />
      </div>

      {/* 右侧：追问区（透出玻璃氛围，不用白底） */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶部：身份 + 三入口 */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
          <div className="flex items-center gap-2.5">
            <Logo variant="mark" className="h-7 w-7 shrink-0 rounded-full" />
            <div className="min-w-0">
              <div className="text-sm font-semibold">{t('step5.cTitle')}</div>
              <div className="text-muted-foreground text-xs">{t('step5.cSubtitle')}</div>
            </div>
          </div>

          <div className="bg-muted/50 flex items-center gap-1 rounded-full border p-1">
            <SegBtn active={tab === 'super'} onClick={selectSuper} icon={Sparkles}>
              {t('step5.cAskSuper')}
            </SegBtn>
            {profiles.length > 0 && (
              <>
                <SegBtn active={tab === 'one'} onClick={selectOne} icon={User}>
                  {t('step5.cAskOne')}
                </SegBtn>
                <SegBtn active={tab === 'crowd'} onClick={selectCrowd} icon={Users}>
                  {t('step5.cAskCrowd')}
                </SegBtn>
              </>
            )}
          </div>
        </div>

        {/* 内容区 */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {wakingEnv && (
            <div className="flex items-center justify-center gap-2 border-b bg-indigo-500/10 px-4 py-2 text-xs text-indigo-600 dark:text-indigo-300">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {t('step5.cWaking')}
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-hidden">
            {tab === 'crowd' ? (
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
            ) : tab === 'one' && selectedAgentIndex === null ? (
              <PeoplePicker profiles={profiles} onPick={pickAgent} />
            ) : tab === 'one' ? (
              <div className="flex h-full flex-col">
                <button
                  type="button"
                  onClick={backToPicker}
                  className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 border-b px-4 py-2 text-xs transition-colors"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  {t('step5.cChangePerson')}
                </button>
                <div className="min-h-0 flex-1">
                  <ChatPanel
                    target="agent"
                    agent={selectedAgent}
                    messages={currentMessages}
                    isSending={isSending}
                    onSend={sendMessage}
                  />
                </div>
              </div>
            ) : (
              <ChatPanel
                target="report_agent"
                agent={null}
                messages={currentMessages}
                isSending={isSending}
                onSend={sendMessage}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/** 顶部三入口分段按钮 */
function SegBtn({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active?: boolean
  onClick: () => void
  icon: typeof Sparkles
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition',
        active
          ? 'bg-gradient-to-r from-indigo-500 to-fuchsia-500 text-white shadow-sm'
          : 'text-muted-foreground hover:text-foreground',
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </button>
  )
}

/** 选人墙：挑一个推演里的人来追问 */
function PeoplePicker({
  profiles,
  onPick,
}: {
  profiles: Profile[]
  onPick: (idx: number) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="h-full overflow-y-auto px-5 py-6">
      <p className="text-muted-foreground mb-4 text-center text-sm">{t('step5.cPickPrompt')}</p>
      <div className="mx-auto grid max-w-2xl gap-3 sm:grid-cols-2">
        {profiles.map((p, idx) => (
          <button
            key={p.username || idx}
            type="button"
            onClick={() => onPick(idx)}
            className="bg-card flex items-start gap-3 rounded-2xl border p-4 text-left transition-transform duration-300 hover:-translate-y-0.5"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-sm font-medium text-white">
              {initial(p.name || p.username)}
            </div>
            <div className="min-w-0">
              <div className="truncate font-medium">{p.name || p.username}</div>
              <div className="text-muted-foreground truncate text-xs">
                {p.profession || t('step2.unknownProfession')}
              </div>
              {p.bio && (
                <p className="text-muted-foreground mt-1 line-clamp-2 text-xs leading-relaxed">
                  {p.bio}
                </p>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
