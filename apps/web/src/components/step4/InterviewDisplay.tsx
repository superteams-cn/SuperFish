import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Globe, MessageCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { InterviewRecord, InterviewResult } from '@/lib/step4-types'
import { ToolResultShell } from './tool-display-shared'

const PLACEHOLDERS = new Set(['（该平台未获得回复）', '(该平台未获得回复)', '[无回复]'])
const isPlaceholder = (text: string) => !text || PLACEHOLDERS.has(text.trim())

/** 按问题编号把整段回答拆分为各问题对应片段（兼容 "问题X：" 与 "1." 两种格式）。 */
function splitAnswerByQuestions(answerText: string): string[] {
  if (!answerText || isPlaceholder(answerText)) return ['']
  const collect = (re: RegExp) => {
    const out: { index: number; len: number }[] = []
    let m: RegExpExecArray | null
    while ((m = re.exec(answerText)) !== null) out.push({ index: m.index, len: m[0].length })
    return out
  }
  let matches = collect(/(?:^|[\r\n]+)问题(\d+)[：:]\s*/g)
  if (matches.length === 0) matches = collect(/(?:^|[\r\n]+)(\d+)\.\s+/g)
  if (matches.length <= 1) {
    const cleaned = answerText
      .replace(/^问题\d+[：:]\s*/, '')
      .replace(/^\d+\.\s+/, '')
      .trim()
    return [cleaned || answerText]
  }
  const parts: string[] = []
  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].index + matches[i].len
    const end = i + 1 < matches.length ? matches[i + 1].index : answerText.length
    parts.push(
      answerText
        .substring(start, end)
        .replace(/[\r\n]+$/, '')
        .trim(),
    )
  }
  return parts.some((p) => p) ? parts : [answerText]
}

function answerForQuestion(
  interview: InterviewRecord,
  qIdx: number,
  platform: 'twitter' | 'reddit',
) {
  const answer =
    platform === 'twitter'
      ? interview.twitterAnswer
      : interview.redditAnswer || interview.twitterAnswer
  if (!answer || isPlaceholder(answer)) return answer || ''
  const answers = splitAnswerByQuestions(answer)
  if (answers.length > 1 && qIdx < answers.length) return answers[qIdx] || ''
  return qIdx === 0 ? answer : ''
}

function renderInline(text: string) {
  // 轻量内联格式：**加粗** + 换行；其余按纯文本处理。
  return text.split('\n').map((line, i) => {
    const segs = line.split(/(\*\*[^*]+\*\*)/g).filter(Boolean)
    return (
      <span key={i}>
        {segs.map((seg, j) =>
          seg.startsWith('**') && seg.endsWith('**') ? (
            <strong key={j}>{seg.slice(2, -2)}</strong>
          ) : (
            <span key={j}>{seg}</span>
          ),
        )}
        <br />
      </span>
    )
  })
}

/** interview_agents（Agent 采访）结构化展示：受访者切换 + 一问一答 + 双平台 + 关键引言。 */
export function InterviewDisplay({
  result,
  resultLength,
}: {
  result: InterviewResult
  resultLength?: number
}) {
  const { t } = useTranslation()
  const [activeIdx, setActiveIdx] = useState(0)
  const [platforms, setPlatforms] = useState<Record<string, 'twitter' | 'reddit'>>({})
  const [expandedAnswers, setExpandedAnswers] = useState<Set<string>>(new Set())

  const interview = result.interviews[activeIdx]

  const getPlatform = (qIdx: number): 'twitter' | 'reddit' =>
    platforms[`${activeIdx}-${qIdx}`] || 'twitter'
  const setPlatform = (qIdx: number, p: 'twitter' | 'reddit') =>
    setPlatforms((prev) => ({ ...prev, [`${activeIdx}-${qIdx}`]: p }))

  const toggleAnswer = (key: string) =>
    setExpandedAnswers((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const hasDualPlatform = (it: InterviewRecord, qIdx: number) => {
    if (!it.twitterAnswer || !it.redditAnswer) return false
    const a = answerForQuestion(it, qIdx, 'twitter')
    const b = answerForQuestion(it, qIdx, 'reddit')
    return !isPlaceholder(a) && !isPlaceholder(b) && a !== b
  }

  const stats: { label: string; value: number | string }[] = [
    { label: t('step4.statInterviewed'), value: result.successCount || result.interviews.length },
  ]
  if (result.totalCount > 0) stats.push({ label: t('step4.statTotal'), value: result.totalCount })

  return (
    <ToolResultShell
      title={t('step4.toolAgentInterview')}
      stats={stats}
      resultLength={resultLength}
      query={result.topic || undefined}
    >
      {/* 受访者切换 */}
      {result.interviews.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {result.interviews.map((it, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setActiveIdx(i)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px] transition-colors',
                activeIdx === i
                  ? 'bg-brand text-white'
                  : 'bg-muted text-muted-foreground hover:text-foreground',
              )}
            >
              <span className="bg-background/30 flex h-4 w-4 items-center justify-center rounded-full text-[9px]">
                {it.name ? it.name.charAt(0) : i + 1}
              </span>
              {it.title || it.name || `Agent ${i + 1}`}
            </button>
          ))}
        </div>
      )}

      {interview && (
        <div className="space-y-2.5">
          {/* 受访者档案 */}
          <div className="bg-muted/50 flex items-start gap-2 rounded-md p-2">
            <div className="bg-brand flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white">
              {interview.name?.charAt(0) || 'A'}
            </div>
            <div className="min-w-0">
              <div className="text-xs font-semibold">{interview.name || 'Agent'}</div>
              {interview.role && (
                <div className="text-muted-foreground text-[10px]">{interview.role}</div>
              )}
              {interview.bio && (
                <div className="text-muted-foreground mt-0.5 text-[10px] leading-snug">
                  {interview.bio}
                </div>
              )}
            </div>
          </div>

          {/* 选择理由 */}
          {interview.selectionReason && (
            <div className="border-brand/40 bg-brand/5 rounded border-l-2 p-2">
              <div className="text-brand mb-0.5 text-[10px] font-semibold">
                {t('step4.selectionReason')}
              </div>
              <div className="text-[11px] leading-snug">{interview.selectionReason}</div>
            </div>
          )}

          {/* 一问一答 */}
          <div className="space-y-2">
            {(interview.questions.length > 0 ? interview.questions : ['']).map((question, qIdx) => {
              const platform = getPlatform(qIdx)
              const answer = answerForQuestion(interview, qIdx, platform)
              const dual = hasDualPlatform(interview, qIdx)
              const key = `${activeIdx}-${qIdx}`
              const expanded = expandedAnswers.has(key)
              const placeholder = isPlaceholder(answer)
              const displayAnswer =
                expanded || answer.length <= 400 ? answer : answer.slice(0, 400) + '...'

              return (
                <div key={qIdx} className="space-y-1">
                  {/* 问题 */}
                  <div className="flex gap-1.5">
                    <span className="bg-foreground/80 flex h-5 shrink-0 items-center rounded px-1.5 text-[10px] font-semibold text-white">
                      Q{qIdx + 1}
                    </span>
                    <div className="text-[11px] font-medium leading-snug">{question}</div>
                  </div>
                  {/* 回答 */}
                  {answer && (
                    <div className="flex gap-1.5">
                      <span className="bg-brand flex h-5 shrink-0 items-center rounded px-1.5 text-[10px] font-semibold text-white">
                        A{qIdx + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        {dual && (
                          <div className="mb-1 inline-flex gap-1">
                            <PlatformBtn
                              active={platform === 'twitter'}
                              onClick={() => setPlatform(qIdx, 'twitter')}
                              icon={<Globe className="h-2.5 w-2.5" />}
                              label={t('step4.world1')}
                            />
                            <PlatformBtn
                              active={platform === 'reddit'}
                              onClick={() => setPlatform(qIdx, 'reddit')}
                              icon={<MessageCircle className="h-2.5 w-2.5" />}
                              label={t('step4.world2')}
                            />
                          </div>
                        )}
                        <div
                          className={cn(
                            'text-[11px] leading-snug',
                            placeholder && 'text-muted-foreground italic',
                          )}
                        >
                          {placeholder ? answer : renderInline(displayAnswer)}
                        </div>
                        {!placeholder && answer.length > 400 && (
                          <Button
                            variant="link"
                            size="sm"
                            className="text-brand h-auto p-0 text-[10px]"
                            onClick={() => toggleAnswer(key)}
                          >
                            {expanded ? t('step4.collapse') : t('step4.showMore')}
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* 关键引言 */}
          {interview.quotes.length > 0 && (
            <div className="space-y-1">
              <div className="text-muted-foreground text-[10px] font-semibold">
                {t('step4.keyQuotes')}
              </div>
              {interview.quotes.slice(0, 3).map((quote, i) => (
                <blockquote
                  key={i}
                  className="border-brand/40 text-muted-foreground border-l-2 pl-2 text-[11px] italic leading-snug"
                >
                  {quote.length > 200 ? quote.slice(0, 200) + '...' : quote}
                </blockquote>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 采访摘要 */}
      {result.summary && (
        <div className="bg-muted/40 rounded p-2">
          <div className="text-muted-foreground mb-0.5 text-[10px] font-semibold">
            {t('step4.interviewSummary')}
          </div>
          <div className="text-[11px] leading-snug">
            {result.summary.length > 500 ? result.summary.slice(0, 500) + '...' : result.summary}
          </div>
        </div>
      )}
    </ToolResultShell>
  )
}

function PlatformBtn({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] transition-colors',
        active ? 'bg-brand text-white' : 'bg-muted text-muted-foreground hover:text-foreground',
      )}
    >
      {icon}
      {label}
    </button>
  )
}
