import { useTranslation } from 'react-i18next'
import { Loader2, MessageCircleQuestion } from 'lucide-react'

import { Markdown } from '@/components/Markdown'
import { Button } from '@/components/ui/button'
import { SelectableCard } from '@/components/ui/selectable-card'
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

const initial = (name?: string) => (name || 'A').charAt(0).toUpperCase()

/** 问一群人：挑几个人 + 同一个问题 → 收集每个人的回答。 */
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
    <div className="flex h-full flex-col overflow-y-auto px-5 py-5">
      {/* 挑人 */}
      <div className="mb-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">
            {t('step5.cCrowdPick', { count: selected.size })}
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
          {profiles.map((p, idx) => {
            const on = selected.has(idx)
            return (
              <SelectableCard
                key={p.username || idx}
                surface="plain"
                lift={!on}
                onClick={() => onToggle(idx)}
                className={cn(
                  'flex items-center gap-2 rounded-xl border p-2',
                  on ? 'border-indigo-400 bg-indigo-500/10' : 'bg-card',
                )}
              >
                <div
                  className={cn(
                    'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
                    on ? 'bg-brand-gradient text-white' : 'bg-muted text-muted-foreground',
                  )}
                >
                  {initial(p.name || p.username)}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium">
                    {p.name || p.username || `#${idx}`}
                  </div>
                  <div className="text-muted-foreground truncate text-[10px]">{p.profession}</div>
                </div>
              </SelectableCard>
            )
          })}
        </div>
      </div>

      {/* 问题 */}
      <div className="mb-5">
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder={t('step5.cCrowdPlaceholder')}
          className="resize-none rounded-2xl"
        />
        <Button
          variant="gradient"
          className="mt-2 gap-1.5 rounded-full"
          onClick={onSubmit}
          disabled={isSurveying || selected.size === 0 || !question.trim()}
        >
          {isSurveying && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {t('step5.cCrowdSubmit', { count: selected.size })}
        </Button>
      </div>

      {/* 大家的回答 */}
      {results.length > 0 && (
        <div className="space-y-3">
          <span className="text-sm font-medium">
            {t('step5.cCrowdResults', { count: results.length })}
          </span>
          {results.map((r) => (
            <div key={r.agent_id} className="bg-card rounded-2xl border p-4">
              <div className="mb-2 flex items-center gap-2.5">
                <div className="bg-brand-gradient flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white">
                  {initial(r.agent_name)}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{r.agent_name}</div>
                  <div className="text-muted-foreground truncate text-[11px]">
                    {r.profession || t('step2.unknownProfession')}
                  </div>
                </div>
              </div>
              <div className="text-muted-foreground mb-2 flex items-start gap-1.5 text-xs">
                <MessageCircleQuestion className="mt-0.5 h-3.5 w-3.5 shrink-0" />
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
