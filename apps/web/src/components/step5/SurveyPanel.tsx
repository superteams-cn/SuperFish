import { useTranslation } from 'react-i18next'
import { Loader2, HelpCircle } from 'lucide-react'

import { Markdown } from '@/components/Markdown'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { Profile } from '@/lib/step2-types'
import type { SurveyResult } from '@/lib/step5-types'

interface Props {
  profiles: Profile[]
  selected: Set<number>
  onToggle: (idx: number) => void
  onSelectAll: () => void
  onClear: () => void
  question: string
  setQuestion: (v: string) => void
  isSurveying: boolean
  results: SurveyResult[]
  onSubmit: () => void
}

/** 问卷面板：多选 Agent + 提问 + 批量采访结果。 */
export function SurveyPanel({
  profiles,
  selected,
  onToggle,
  onSelectAll,
  onClear,
  question,
  setQuestion,
  isSurveying,
  results,
  onSubmit,
}: Props) {
  const { t } = useTranslation()

  return (
    <div className="flex h-full flex-col overflow-y-auto p-4">
      {/* Agent 多选 */}
      <div className="mb-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold">
            {t('step5.selectAgents')} ({selected.size})
          </span>
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={onSelectAll}>
              {t('step5.selectAll')}
            </Button>
            <Button variant="ghost" size="sm" onClick={onClear}>
              {t('step5.clear')}
            </Button>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {profiles.map((p, idx) => (
            <button
              key={idx}
              onClick={() => onToggle(idx)}
              className={cn(
                'rounded-md border px-2 py-1.5 text-left text-xs transition',
                selected.has(idx) ? 'border-brand bg-brand/10' : 'hover:bg-accent',
              )}
            >
              <div className="truncate font-medium">{p.username || `Agent ${idx}`}</div>
              <div className="text-muted-foreground truncate text-[10px]">{p.profession}</div>
            </button>
          ))}
        </div>
      </div>

      {/* 提问 */}
      <div className="mb-4">
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder={t('step5.surveyPlaceholder')}
          className="resize-none"
        />
        <Button
          className="mt-2"
          size="sm"
          onClick={onSubmit}
          disabled={isSurveying || selected.size === 0 || !question.trim()}
        >
          {isSurveying && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {t('step5.submitSurvey')}
        </Button>
      </div>

      {/* 结果 */}
      {results.length > 0 && (
        <div className="space-y-3">
          <span className="text-sm font-semibold">
            {t('step5.surveyResults')} ({results.length})
          </span>
          {results.map((r) => (
            <div key={r.agent_id} className="rounded-md border p-3">
              <div className="mb-2 flex items-center gap-2">
                <Avatar className="h-8 w-8 shrink-0">
                  <AvatarFallback className="bg-brand text-[11px] font-semibold text-white">
                    {(r.agent_name || 'A').charAt(0).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{r.agent_name}</div>
                  <div className="text-muted-foreground truncate text-[10px]">
                    {r.profession || t('step2.unknownProfession')}
                  </div>
                </div>
              </div>
              <div className="text-muted-foreground mb-2 flex items-start gap-1.5 text-xs">
                <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{r.question}</span>
              </div>
              <Markdown content={r.answer} className="text-[13px]" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
