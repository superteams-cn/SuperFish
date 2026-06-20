import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowUp, User } from 'lucide-react'

import { Logo } from '@/components/common/Logo'
import { Markdown } from '@/components/Markdown'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { Profile } from '@/lib/step2-types'
import type { ChatMessage } from '@/lib/step5-types'

interface Props {
  /** 对话对象：SuperFish 分析师 或 推演里的某个人 */
  target: 'report_agent' | 'agent'
  /** target === 'agent' 时选中的个体 */
  agent?: Profile | null
  messages: ChatMessage[]
  isSending: boolean
  onSend: (text: string) => void
}

const GRADIENT = 'bg-gradient-to-br from-indigo-500 to-fuchsia-500'
const initial = (name?: string) => (name || '?').charAt(0).toUpperCase()

/**
 * C 端追问对话面板：和「SuperFish 分析师」或「推演里的某个人」对话。
 * 延续首页对话气质——引导式空状态 + 示例问题 + 玻璃气泡 + 打字指示。
 * 长滚动区用不透明背景，气泡用实色，避免透出动画背景导致卡顿。
 */
export function ChatPanel({ target, agent, messages, isSending, onSend }: Props) {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const isReport = target === 'report_agent'
  const agentName = agent?.name || agent?.username
  const senderName = isReport ? t('step5.reportAgentName') : agentName || t('step5.someone')

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isSending])

  const send = () => {
    const text = input.trim()
    if (!text || isSending) return
    onSend(text)
    setInput('')
  }

  const examples = isReport
    ? [t('step5.exReportA'), t('step5.exReportB'), t('step5.exReportC')]
    : [t('step5.exAgentA'), t('step5.exAgentB')]

  const AssistantAvatar = () =>
    isReport ? (
      <Logo variant="mark" className="h-8 w-8 shrink-0 rounded-full shadow-sm" />
    ) : (
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white',
          GRADIENT,
        )}
      >
        {initial(agentName)}
      </div>
    )

  return (
    <div className="flex h-full flex-col">
      {/* 对话对象简介（人话，无工具黑话） */}
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <AssistantAvatar />
        <div className="min-w-0">
          <div className="text-sm font-semibold">{senderName}</div>
          <div className="text-muted-foreground truncate text-xs">
            {isReport
              ? t('step5.reportAgentTagline')
              : agent?.profession || t('step2.unknownProfession')}
          </div>
        </div>
      </div>

      {/* 消息流 */}
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5">
        {messages.length === 0 && (
          <div className="mx-auto mt-6 max-w-md text-center">
            <p className="text-muted-foreground text-sm leading-relaxed">
              {isReport
                ? t('step5.chatEmptyReportAgent')
                : t('step5.chatEmptyAgent', { name: agentName || t('step5.someone') })}
            </p>
            <div className="mt-4 flex flex-col items-stretch gap-2">
              {examples.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => !isSending && onSend(ex)}
                  disabled={isSending}
                  className="bg-muted hover:bg-accent rounded-full px-4 py-2 text-sm transition disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => {
          const isUser = msg.role === 'user'
          return (
            <div key={idx} className={cn('flex gap-2.5', isUser ? 'flex-row-reverse' : 'flex-row')}>
              {isUser ? (
                <div className="bg-muted text-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-full">
                  <User className="h-4 w-4" />
                </div>
              ) : (
                <AssistantAvatar />
              )}
              <div
                className={cn(
                  'max-w-[78%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed',
                  isUser ? `${GRADIENT} text-white` : 'bg-muted text-foreground',
                )}
              >
                {isUser ? (
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <Markdown content={msg.content} />
                )}
              </div>
            </div>
          )
        })}

        {isSending && (
          <div className="flex gap-2.5">
            <AssistantAvatar />
            <div className="bg-muted flex items-center rounded-2xl px-3.5 py-3">
              <TypingIndicator />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* 输入 */}
      <div className="border-t p-3">
        <div className="bg-muted/60 flex items-end gap-2 rounded-2xl border px-2 py-1.5">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            rows={1}
            placeholder={t('step5.inputPlaceholder')}
            className="max-h-32 min-h-[2.25rem] flex-1 resize-none border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0"
          />
          <button
            type="button"
            onClick={send}
            disabled={isSending || !input.trim()}
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white transition',
              GRADIENT,
              (isSending || !input.trim()) && 'opacity-40',
            )}
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

/** 三点跳动的「正在输入」指示器 */
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
