import { useTranslation } from 'react-i18next'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'
import type { ActionItem } from '@/lib/step3-types'

const TYPE_LABELS: Record<string, string> = {
  CREATE_POST: 'POST',
  REPOST: 'REPOST',
  LIKE_POST: 'LIKE',
  CREATE_COMMENT: 'COMMENT',
  LIKE_COMMENT: 'LIKE',
  DO_NOTHING: 'IDLE',
  FOLLOW: 'FOLLOW',
  SEARCH_POSTS: 'SEARCH',
  QUOTE_POST: 'QUOTE',
  UPVOTE_POST: 'UPVOTE',
  DOWNVOTE_POST: 'DOWNVOTE',
}

const TYPE_COLORS: Record<string, string> = {
  CREATE_POST: 'bg-[#FF5722] text-white',
  QUOTE_POST: 'bg-[#FF5722] text-white',
  CREATE_COMMENT: 'bg-blue-500 text-white',
  DO_NOTHING: 'bg-muted text-muted-foreground',
}

function label(type?: string) {
  return (type && TYPE_LABELS[type]) || type || 'UNKNOWN'
}
function badgeColor(type?: string) {
  return (type && TYPE_COLORS[type]) || 'bg-secondary text-secondary-foreground'
}
function truncate(content?: string, max = 100) {
  if (!content) return ''
  return content.length > max ? content.substring(0, max) + '...' : content
}
function actionTime(ts?: string) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ''
  }
}

/** 时间线中的单条 Agent 动作卡片，按动作类型渲染不同正文。 */
export function ActionCard({ action }: { action: ActionItem }) {
  const { t } = useTranslation()
  const args = action.action_args || {}
  const type = action.action_type

  return (
    <div className="relative pl-6">
      <span
        className={cn(
          'absolute left-0 top-2 h-2.5 w-2.5 rounded-full border-2 border-background',
          action.platform === 'twitter' ? 'bg-sky-500' : 'bg-orange-500',
        )}
      />
      <div className="rounded-md border bg-card p-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Avatar className="h-6 w-6">
              <AvatarFallback className="text-[10px]">{(action.agent_name || 'A')[0]}</AvatarFallback>
            </Avatar>
            <span className="text-xs font-semibold">{action.agent_name}</span>
          </div>
          <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-semibold', badgeColor(type))}>
            {label(type)}
          </span>
        </div>

        <div className="space-y-1.5 text-[11px] leading-relaxed">
          {type === 'CREATE_POST' && args.content && <p>{args.content}</p>}

          {type === 'QUOTE_POST' && (
            <>
              {args.quote_content && <p>{args.quote_content}</p>}
              {args.original_content && (
                <div className="rounded border-l-2 border-muted bg-muted/40 p-2">
                  <span className="text-[10px] text-muted-foreground">
                    @{args.original_author_name || 'User'}
                  </span>
                  <p>{truncate(args.original_content, 150)}</p>
                </div>
              )}
            </>
          )}

          {type === 'REPOST' && (
            <>
              <p className="text-muted-foreground">
                {t('step3.repostedFrom', { name: args.original_author_name || 'User' })}
              </p>
              {args.original_content && (
                <p className="rounded bg-muted/40 p-2">{truncate(args.original_content, 200)}</p>
              )}
            </>
          )}

          {type === 'LIKE_POST' && (
            <>
              <p className="text-muted-foreground">
                {t('step3.likedPost', { name: args.post_author_name || 'User' })}
              </p>
              {args.post_content && <p className="italic">"{truncate(args.post_content, 120)}"</p>}
            </>
          )}

          {type === 'CREATE_COMMENT' && (
            <>
              {args.content && <p>{args.content}</p>}
              {args.post_id && (
                <p className="text-[10px] text-muted-foreground">
                  {t('step3.replyToPost', { id: args.post_id })}
                </p>
              )}
            </>
          )}

          {type === 'SEARCH_POSTS' && (
            <p className="text-muted-foreground">
              {t('step3.searchQueryLabel')} <span className="font-mono">"{args.query || ''}"</span>
            </p>
          )}

          {type === 'FOLLOW' && (
            <p className="text-muted-foreground">
              {t('step3.followed', { name: args.target_user || args.user_id || 'User' })}
            </p>
          )}

          {(type === 'UPVOTE_POST' || type === 'DOWNVOTE_POST') && (
            <>
              <p className="text-muted-foreground">
                {type === 'UPVOTE_POST' ? t('step3.upvotedPost') : t('step3.downvotedPost')}
              </p>
              {args.post_content && <p className="italic">"{truncate(args.post_content, 120)}"</p>}
            </>
          )}

          {type === 'DO_NOTHING' && (
            <p className="text-muted-foreground">{t('step3.actionSkipped')}</p>
          )}

          {/* 通用回退 */}
          {![
            'CREATE_POST',
            'QUOTE_POST',
            'REPOST',
            'LIKE_POST',
            'CREATE_COMMENT',
            'SEARCH_POSTS',
            'FOLLOW',
            'UPVOTE_POST',
            'DOWNVOTE_POST',
            'DO_NOTHING',
          ].includes(type || '') &&
            args.content && <p>{args.content}</p>}
        </div>

        <div className="mt-2 text-[10px] text-muted-foreground">
          R{action.round_num} • {actionTime(action.timestamp)}
        </div>
      </div>
    </div>
  )
}
