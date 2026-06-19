import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Send, User, ChevronDown, Brain, Globe, Zap, Users, Wrench } from 'lucide-react'

import { Markdown } from '@/components/Markdown'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { Profile } from '@/lib/step2-types'
import type { ChatMessage, ToolCall } from '@/lib/step5-types'

interface Props {
  /** 对话对象：报告智能体 或 模拟世界中的某个 Agent */
  target: 'report_agent' | 'agent'
  /** target === 'agent' 时选中的个体 */
  agent?: Profile | null
  messages: ChatMessage[]
  isSending: boolean
  onSend: (text: string) => void
}

function formatTime(ts?: string) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

const initial = (name?: string) => (name || 'A').charAt(0).toUpperCase()

/** 通用聊天面板：消息气泡列表 + 输入框（与 ReportAgent / 单个 Agent 复用）。 */
export function ChatPanel({ target, agent, messages, isSending, onSend }: Props) {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const isReportAgent = target === 'report_agent'
  const senderName = isReportAgent ? t('step5.reportAgentName') : agent?.username || 'Agent'
  const senderInitial = isReportAgent ? 'R' : initial(agent?.username)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isSending])

  const send = () => {
    const text = input.trim()
    if (!text || isSending) return
    onSend(text)
    setInput('')
  }

  const assistantAvatar = (
    <Avatar className="h-8 w-8">
      <AvatarFallback className="bg-brand text-[11px] font-semibold text-white">
        {senderInitial}
      </AvatarFallback>
    </Avatar>
  )

  return (
    <div className="flex h-full flex-col">
      {/* 对话对象信息卡 */}
      {isReportAgent ? <ReportAgentToolsCard /> : agent && <AgentProfileCard agent={agent} />}

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-muted-foreground mt-8 text-center text-sm">
            {isReportAgent ? t('step5.chatEmptyReportAgent') : t('step5.chatEmptyAgent')}
          </p>
        )}
        {messages.map((msg, idx) => {
          const isUser = msg.role === 'user'
          return (
            <div key={idx} className={cn('flex gap-2', isUser ? 'flex-row-reverse' : 'flex-row')}>
              <Avatar className="h-8 w-8 shrink-0">
                <AvatarFallback
                  className={cn(
                    'text-[11px] font-semibold',
                    isUser ? 'bg-muted text-foreground' : 'bg-brand text-white',
                  )}
                >
                  {isUser ? <User className="h-4 w-4" /> : senderInitial}
                </AvatarFallback>
              </Avatar>
              <div className={cn('min-w-0 max-w-[80%]', isUser ? 'items-end' : 'items-start')}>
                <div
                  className={cn(
                    'mb-1 flex items-baseline gap-2',
                    isUser ? 'flex-row-reverse' : 'flex-row',
                  )}
                >
                  <span className="text-xs font-semibold">
                    {isUser ? t('step5.youName') : senderName}
                  </span>
                  <span className="text-muted-foreground text-[10px]">
                    {formatTime(msg.timestamp)}
                  </span>
                </div>
                <div
                  className={cn(
                    'rounded-lg px-3 py-2 text-sm',
                    isUser ? 'bg-brand text-white' : 'bg-card border',
                  )}
                >
                  {isUser ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <Markdown content={msg.content} />
                  )}
                </div>
                {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
                  <ToolCallsLog calls={msg.toolCalls} />
                )}
              </div>
            </div>
          )
        })}
        {isSending && (
          <div className="flex flex-row gap-2">
            {assistantAvatar}
            <div className="bg-card flex items-center rounded-lg border px-3 py-3">
              <TypingIndicator />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t p-3">
        <div className="flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            rows={2}
            placeholder={t('step5.inputPlaceholder')}
            className="flex-1 resize-none"
          />
          <Button
            size="icon"
            className="h-auto"
            onClick={send}
            disabled={isSending || !input.trim()}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

/** 三点跳动的“正在输入”指示器 */
function TypingIndicator() {
  return (
    <span className="flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="bg-muted-foreground/60 h-1.5 w-1.5 animate-bounce rounded-full"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  )
}

const TOOLS = [
  { key: 'InsightForge', icon: Brain, color: 'text-violet-500 bg-violet-500/10' },
  { key: 'PanoramaSearch', icon: Globe, color: 'text-blue-500 bg-blue-500/10' },
  { key: 'QuickSearch', icon: Zap, color: 'text-orange-500 bg-orange-500/10' },
  { key: 'InterviewSubAgent', icon: Users, color: 'text-green-500 bg-green-500/10' },
] as const

/** ReportAgent 工具说明卡（可折叠，展示 4 个专业工具） */
function ReportAgentToolsCard() {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="from-muted/40 to-muted/10 border-b bg-gradient-to-br">
      <div className="flex items-center gap-3 px-4 py-3">
        <Avatar className="h-10 w-10">
          <AvatarFallback className="bg-brand text-sm font-semibold text-white">R</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{t('step5.reportAgentChat')}</div>
          <div className="text-muted-foreground truncate text-xs">{t('step5.reportAgentDesc')}</div>
        </div>
        <Button
          variant="outline"
          size="icon"
          className="h-7 w-7 shrink-0"
          onClick={() => setExpanded((v) => !v)}
          aria-label={t('step5.toggleTools')}
        >
          <ChevronDown className={cn('h-4 w-4 transition-transform', expanded && 'rotate-180')} />
        </Button>
      </div>
      {expanded && (
        <div className="grid grid-cols-1 gap-2 px-4 pb-3 sm:grid-cols-2">
          {TOOLS.map(({ key, icon: Icon, color }) => (
            <div key={key} className="bg-card flex gap-2 rounded-lg border p-3">
              <div
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                  color,
                )}
              >
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold">{t(`step5.tool${key}`)}</div>
                <div className="text-muted-foreground line-clamp-2 text-[11px] leading-snug">
                  {t(`step5.tool${key}Desc`)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** 选中 Agent 的档案卡（username / @name / profession + 可展开 bio） */
function AgentProfileCard({ agent }: { agent: Profile }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(true)
  const hasBio = !!agent.bio

  return (
    <div className="from-muted/40 to-muted/10 border-b bg-gradient-to-br">
      <div className="flex items-center gap-3 px-4 py-3">
        <Avatar className="h-10 w-10">
          <AvatarFallback className="bg-brand text-sm font-semibold text-white">
            {initial(agent.username)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">{agent.username || 'Agent'}</div>
          <div className="text-muted-foreground flex items-center gap-2 text-xs">
            {agent.name && <span className="text-muted-foreground/70">@{agent.name}</span>}
            <span className="bg-muted rounded px-1.5 py-0.5 text-[10px] font-medium">
              {agent.profession || t('step2.unknownProfession')}
            </span>
          </div>
        </div>
        {hasBio && (
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7 shrink-0"
            onClick={() => setExpanded((v) => !v)}
            aria-label={t('step5.toggleProfile')}
          >
            <ChevronDown className={cn('h-4 w-4 transition-transform', expanded && 'rotate-180')} />
          </Button>
        )}
      </div>
      {expanded && hasBio && (
        <div className="px-4 pb-3">
          <div className="bg-card rounded-lg border p-3">
            <div className="text-muted-foreground mb-1 text-[10px] font-semibold uppercase tracking-wide">
              {t('step5.profileBio')}
            </div>
            <p className="text-foreground/80 text-[13px] leading-relaxed">{agent.bio}</p>
          </div>
        </div>
      )}
    </div>
  )
}

/** 工具调用日志（可折叠，展示本轮回复触发的工具调用） */
function ToolCallsLog({ calls }: { calls: ToolCall[] }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="mt-1.5">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-[11px] transition"
      >
        <Wrench className="h-3 w-3" />
        {t('step5.toolCallsCount', { count: calls.length })}
        <ChevronDown className={cn('h-3 w-3 transition-transform', expanded && 'rotate-180')} />
      </button>
      {expanded && (
        <div className="mt-1 space-y-1">
          {calls.map((c, i) => {
            const name = c.tool_name || c.name || t('step5.unknownTool')
            const params = c.parameters
            return (
              <div key={i} className="bg-muted/50 rounded-md border p-2 text-[11px]">
                <div className="font-mono font-semibold">{name}</div>
                {params && Object.keys(params).length > 0 && (
                  <pre className="text-muted-foreground mt-1 overflow-x-auto whitespace-pre-wrap break-words">
                    {JSON.stringify(params, null, 2)}
                  </pre>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
