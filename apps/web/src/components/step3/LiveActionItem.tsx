import { useTranslation } from 'react-i18next'

import { PlatformLogo } from '@/components/step3/PlatformLogo'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { ActionItem } from '@/lib/step3-types'

function truncate(s?: string, n = 160) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

function actionTime(ts?: string) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('zh-CN', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

/**
 * 实况动作卡片（人话）：把一条 Agent 动作讲成「谁·做了什么·内容」，
 * 隐藏平台/动作代码等黑话，只保留普通人看得懂的叙述。供 Step3 舞台实况流使用。
 */
export function LiveActionItem({ action }: { action: ActionItem }) {
  const { t } = useTranslation()
  const a = action.action_args || {}
  const someone = t('step3.someone')
  const name = action.agent_name || someone
  const type = action.action_type
  const isPlaza = action.platform === 'twitter'
  const loc = isPlaza ? t('step3.cLocPlaza') : t('step3.cLocCommunity')

  let verb = t('step3.vActed')
  let body: string | undefined
  let quote: { author?: string; text?: string } | undefined

  switch (type) {
    case 'CREATE_POST':
      verb = t('step3.vPost')
      body = a.content
      break
    case 'CREATE_COMMENT':
      verb = t('step3.vComment')
      body = a.content
      break
    case 'QUOTE_POST':
      verb = t('step3.vQuote')
      body = a.quote_content
      if (a.original_content) quote = { author: a.original_author_name, text: a.original_content }
      break
    case 'REPOST':
      verb = t('step3.vRepost', { name: a.original_author_name || someone })
      if (a.original_content) quote = { text: a.original_content }
      break
    case 'LIKE_POST':
    case 'LIKE_COMMENT':
      verb = t('step3.vLike', { name: a.post_author_name || someone })
      if (a.post_content) quote = { text: a.post_content }
      break
    case 'UPVOTE_POST':
      verb = t('step3.vUpvote', { name: a.post_author_name || someone })
      if (a.post_content) quote = { text: a.post_content }
      break
    case 'DOWNVOTE_POST':
      verb = t('step3.vDownvote', { name: a.post_author_name || someone })
      if (a.post_content) quote = { text: a.post_content }
      break
    case 'FOLLOW':
      verb = t('step3.vFollow', { name: String(a.target_user || a.user_id || someone) })
      break
    case 'SEARCH_POSTS':
      verb = t('step3.vSearch', { query: String(a.query || '') })
      break
    default:
      body = a.content
  }

  return (
    <Card variant="glass" className="animate-rise-in flex gap-3 p-3.5">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-sm font-medium text-white">
        {name.slice(0, 1)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-1.5">
          <span className="text-sm font-medium">{name}</span>
          <span className="text-muted-foreground text-sm">{verb}</span>
          <span className="ml-auto flex shrink-0 items-center gap-1.5">
            <span className="text-muted-foreground/70 inline-flex items-center gap-1 text-[10px]">
              <PlatformLogo platform={action.platform} className="h-3 w-3" />
              {loc}
            </span>
            <span className="text-muted-foreground/45 text-[10px]">
              {actionTime(action.timestamp)}
            </span>
          </span>
        </div>
        {body && (
          <p className="text-foreground/85 mt-1.5 text-sm leading-relaxed">{truncate(body)}</p>
        )}
        {quote?.text && (
          <div
            className={cn(
              'bg-secondary text-muted-foreground mt-2 rounded-xl border-l-2 border-indigo-300/60 px-3 py-1.5 text-xs leading-relaxed',
            )}
          >
            {quote.author && <span className="mb-0.5 block text-[10px]">@{quote.author}</span>}
            {truncate(quote.text, 120)}
          </div>
        )}
      </div>
    </Card>
  )
}
