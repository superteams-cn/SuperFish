import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { chatWithReport, getReport, getReportSections } from '@/lib/api/report'
import {
  streamInterview,
  streamInterviewBatch,
  getSimulationProfilesRealtime,
  ensureEnv,
  getEnvStatus,
} from '@/lib/api/simulation'
import type { Profile } from '@/lib/step2-types'
import type { ReportOutline } from '@/lib/step4-types'
import type { ChatMessage, SurveyResult, ToolCall } from '@/lib/step5-types'

interface Options {
  reportId: string
  simulationId: string
  addLog: (msg: string) => void
}

type TargetKey = 'report_agent' | `agent_${number}`
/** 追问对象：问 SuperFish / 问一个人 / 问一群人 */
export type Tab = 'super' | 'one' | 'crowd'

/**
 * 步骤五深入追问的全部交互逻辑：报告/档案加载、环境按需唤醒、单人流式采访、群体流式问卷、
 * 追问对象切换。作为「容器 hook」收拢状态与副作用，Step5Interaction 退化为纯展示层。
 * 行为与原内联实现一致。
 */
export function useInteraction({ reportId, simulationId, addLog }: Options) {
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
        // 流式采访：先放一个空的助手气泡，逐 token 追加，体感即时（而非干等数十秒）
        append(key, { role: 'assistant', content: '', timestamp: new Date().toISOString() })
        const setLastAssistant = (content: string) =>
          setHistories((prevH) => {
            const list = prevH[key] || []
            const next = list.slice()
            for (let i = next.length - 1; i >= 0; i--) {
              if (next[i].role === 'assistant') {
                next[i] = { ...next[i], content }
                break
              }
            }
            return { ...prevH, [key]: next }
          })
        let acc = ''
        const errBox: { msg: string | null } = { msg: null }
        await streamInterview(
          { simulation_id: simulationId, agent_id: idx, prompt },
          {
            onChunk: (delta) => {
              acc += delta
              setLastAssistant(acc)
            },
            onDone: (fullText) => {
              acc = fullText || acc
              setLastAssistant(acc || t('step5.noResponse'))
            },
            onError: (e) => {
              errBox.msg = e
            },
          },
        )
        if (errBox.msg) {
          addLog(t('log.sendFailed', { error: errBox.msg }))
          // 唤醒失败/环境已回收 → 人话兜底引导改问 SuperFish
          setLastAssistant(t('step5.cAgentUnavailable'))
        } else {
          addLog(t('log.agentReplied', { name: selectedAgent?.name || selectedAgent?.username }))
        }
        return
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
      const q = question.trim()
      const interviews = Array.from(selected).map((idx) => ({ agent_id: idx, prompt: q }))
      // 先用空答案占位渲染每个人的卡片，随后各自的答案逐 token 并发填充
      const placeholders: SurveyResult[] = interviews.map(({ agent_id }) => {
        const agent = profiles[agent_id]
        return {
          agent_id,
          agent_name: agent?.name || agent?.username || `Agent ${agent_id}`,
          profession: agent?.profession,
          question: q,
          answer: '',
        }
      })
      setSurveyResults(placeholders)

      const acc: Record<number, string> = {}
      const setAnswer = (agentId: number, content: string) =>
        setSurveyResults((prev) =>
          prev.map((r) => (r.agent_id === agentId ? { ...r, answer: content } : r)),
        )
      const errBox: { msg: string | null } = { msg: null }
      await streamInterviewBatch(
        { simulation_id: simulationId, interviews },
        {
          onChunk: (agentId, delta) => {
            acc[agentId] = (acc[agentId] || '') + delta
            setAnswer(agentId, acc[agentId])
          },
          onAgentDone: (agentId, full) => {
            acc[agentId] = full || acc[agentId] || t('step5.noResponse')
            setAnswer(agentId, acc[agentId])
          },
          onAgentError: (agentId) => setAnswer(agentId, t('step5.cAgentUnavailable')),
          onDone: () => addLog(t('log.receivedReplies', { count: interviews.length })),
          onError: (e) => {
            errBox.msg = e
          },
        },
      )
      if (errBox.msg) addLog(t('log.surveySendFailed', { error: errBox.msg }))
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

  /* ── 问卷选择 ─────────────────────────────────────────── */
  const toggleAgent = (idx: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  const selectAllAgents = () => setSelected(new Set(profiles.map((_, i) => i)))
  const clearSelected = () => setSelected(new Set())

  return {
    // 左侧报告
    outline,
    generatedSections,
    // 顶部 / 状态
    tab,
    profiles,
    wakingEnv,
    // 聊天
    currentMessages,
    isSending,
    selectedAgentIndex,
    selectedAgent,
    sendMessage,
    // 问卷
    selected,
    question,
    setQuestion,
    isSurveying,
    surveyResults,
    submitSurvey,
    toggleAgent,
    selectAllAgents,
    clearSelected,
    // 切换
    selectSuper,
    selectOne,
    selectCrowd,
    pickAgent,
    backToPicker,
  }
}
