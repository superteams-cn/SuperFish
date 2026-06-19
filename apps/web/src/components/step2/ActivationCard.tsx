import { useTranslation } from 'react-i18next'
import { Compass } from 'lucide-react'

import { StepCard } from './StepCard'
import type { SimulationConfig } from '@/lib/step2-types'

interface Props {
  phase: number
  config: SimulationConfig | null
  getAgentUsername: (agentId: number) => string
}

/** 步骤 04：初始激活编排（叙事方向 / 热点话题 / 初始帖子流）。 */
export function ActivationCard({ phase, config, getAgentUsername }: Props) {
  const { t } = useTranslation()
  const ec = config?.event_config

  const status = phase > 3 ? 'completed' : phase === 3 ? 'processing' : 'pending'
  const statusText =
    phase > 3 ? t('common.completed') : phase === 3 ? t('step2.orchestrating') : t('common.pending')

  return (
    <StepCard
      num="04"
      title={t('step2.initialActivation')}
      status={status}
      statusText={statusText}
      active={phase === 3}
      apiNote="POST /api/simulation/prepare"
      description={t('step2.initialActivationDesc')}
    >
      {ec && (
        <div className="space-y-4">
          {/* 叙事方向 */}
          <div className="rounded-md border border-[#FF5722]/30 bg-[#FF5722]/5 p-3">
            <span className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold text-[#FF5722]">
              <Compass className="h-4 w-4" />
              {t('step2.narrativeDirection')}
            </span>
            <p className="text-xs leading-relaxed">{ec.narrative_direction}</p>
          </div>

          {/* 热点话题 */}
          {!!ec.hot_topics?.length && (
            <div>
              <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">
                {t('step2.initialHotTopics')}
              </span>
              <div className="flex flex-wrap gap-2">
                {ec.hot_topics.map((topic) => (
                  <span key={topic} className="rounded-full bg-muted px-2.5 py-0.5 text-[11px]">
                    # {topic}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 初始帖子流 */}
          {!!ec.initial_posts?.length && (
            <div>
              <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">
                {t('step2.initialActivationSeq', { count: ec.initial_posts.length })}
              </span>
              <div className="space-y-2 border-l-2 border-muted pl-4">
                {ec.initial_posts.map((post, idx) => (
                  <div key={idx} className="relative">
                    <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-[#FF5722]" />
                    <div className="rounded-md bg-muted/50 p-2.5">
                      <div className="mb-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                        <span className="font-semibold">{post.poster_type}</span>
                        <span className="font-mono">Agent {post.poster_agent_id}</span>
                        <span>@{getAgentUsername(post.poster_agent_id)}</span>
                      </div>
                      <p className="text-[11px] leading-relaxed">{post.content}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </StepCard>
  )
}
