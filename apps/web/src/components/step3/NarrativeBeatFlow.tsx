import { useTranslation } from 'react-i18next'
import { MessageCircle, Brain, Clapperboard } from 'lucide-react'

import type { BeatItem } from '@/lib/narrative-types'

/** 单条 beat 卡片：说话 / 内心独白 / 导演切场 三种形态。 */
function BeatCard({ beat }: { beat: BeatItem }) {
  const { t } = useTranslation()
  const name = beat.actor_name || beat.actor
  const toNames = (beat.to_names || []).filter(Boolean)

  if (beat.type === 'DIRECT') {
    return (
      <div className="animate-rise-in flex items-center justify-center gap-2 py-1">
        <Clapperboard className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
        <span className="text-muted-foreground text-center text-xs italic">{beat.content}</span>
      </div>
    )
  }

  if (beat.type === 'ASIDE') {
    return (
      <div className="animate-rise-in ml-8 flex items-start gap-2">
        <Brain className="mt-0.5 h-4 w-4 shrink-0 text-violet-400" />
        <p className="text-muted-foreground text-sm italic leading-relaxed">
          <span className="font-medium not-italic">{name}</span>
          <span className="mx-1">·</span>
          {t('narrative.inner')}：{beat.content}
        </p>
      </div>
    )
  }

  // SPEAK / ACT / MOVE
  return (
    <div className="animate-rise-in bg-card rounded-2xl border px-4 py-3 shadow-sm backdrop-blur-xl">
      <div className="flex items-center gap-1.5 text-sm font-semibold">
        <MessageCircle className="h-4 w-4 shrink-0 text-indigo-500" />
        <span>{name}</span>
        {toNames.length > 0 && (
          <span className="text-muted-foreground font-normal">
            {t('narrative.speakingTo', { names: toNames.join('、') })}
          </span>
        )}
      </div>
      <p className="mt-1.5 text-sm leading-relaxed">{beat.content}</p>
      {beat.subtext && (
        <p className="text-muted-foreground mt-1.5 border-l-2 border-amber-300/60 pl-2 text-xs italic">
          {t('narrative.subtext')}：{beat.subtext}
        </p>
      )}
    </div>
  )
}

/** beat 流：按发生顺序竖排（最新在底，贴近“剧本逐行展开”的阅读直觉）。 */
export function NarrativeBeatFlow({ beats }: { beats: BeatItem[] }) {
  return (
    <div className="space-y-3">
      {beats.map((b) => (
        <BeatCard key={b._uniqueId || `beat-${b.seq}`} beat={b} />
      ))}
    </div>
  )
}
