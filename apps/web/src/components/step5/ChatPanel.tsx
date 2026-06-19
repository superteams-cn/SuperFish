import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Send, Loader2 } from 'lucide-react'

import { Markdown } from '@/components/Markdown'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { ChatMessage } from '@/lib/step5-types'

interface Props {
  title: string
  subtitle?: string
  messages: ChatMessage[]
  isSending: boolean
  onSend: (text: string) => void
}

function formatTime(ts?: string) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

/** 通用聊天面板：消息气泡列表 + 输入框（与 ReportAgent / 单个 Agent 复用）。 */
export function ChatPanel({ title, subtitle, messages, isSending, onSend }: Props) {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, isSending])

  const send = () => {
    const text = input.trim()
    if (!text || isSending) return
    onSend(text)
    setInput('')
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="mt-8 text-center text-sm text-muted-foreground">
            {t('step5.startConversation', { defaultValue: '开始对话吧' })}
          </p>
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div
              className={cn(
                'max-w-[80%] rounded-lg px-3 py-2 text-sm',
                msg.role === 'user' ? 'bg-[#FF5722] text-white' : 'border bg-card',
              )}
            >
              {msg.role === 'assistant' ? (
                <Markdown content={msg.content} />
              ) : (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}
              <span
                className={cn(
                  'mt-1 block text-[10px]',
                  msg.role === 'user' ? 'text-white/70' : 'text-muted-foreground',
                )}
              >
                {formatTime(msg.timestamp)}
              </span>
            </div>
          </div>
        ))}
        {isSending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('common.processing')}
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
            placeholder={t('step5.inputPlaceholder', { defaultValue: '输入消息，回车发送' })}
            className="flex-1 resize-none"
          />
          <Button size="icon" className="h-auto" onClick={send} disabled={isSending || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
