import { useTranslation } from 'react-i18next'

import { StepCard } from './StepCard'
import type { Profile } from '@/lib/step2-types'

interface Props {
  phase: number
  profiles: Profile[]
  expectedTotal: number | null
  prepareProgress: number
  onSelectProfile: (p: Profile) => void
}

/** 步骤 02：生成 Agent 人设（统计 + 人设卡片列表）。 */
export function AgentPersonaCard({
  phase,
  profiles,
  expectedTotal,
  prepareProgress,
  onSelectProfile,
}: Props) {
  const { t } = useTranslation()

  const totalTopics = profiles.reduce((sum, p) => sum + (p.interested_topics?.length || 0), 0)

  const status = phase > 1 ? 'completed' : phase === 1 ? 'processing' : 'pending'
  const statusText =
    phase > 1 ? t('common.completed') : phase === 1 ? `${prepareProgress}%` : t('common.pending')

  return (
    <StepCard
      num="02"
      title={t('step2.generateAgentPersona')}
      status={status}
      statusText={statusText}
      active={phase === 1}
      apiNote="POST /api/simulation/prepare"
      description={t('step2.generateAgentPersonaDesc')}
    >
      {profiles.length > 0 && (
        <>
          <div className="mb-4 grid grid-cols-3 gap-3 rounded-md bg-muted/50 p-4">
            {[
              { v: profiles.length, l: t('step2.currentAgentCount') },
              { v: expectedTotal || '-', l: t('step2.expectedAgentTotal') },
              { v: totalTopics, l: t('step2.relatedTopicsCount') },
            ].map((s, i) => (
              <div key={i} className="text-center">
                <span className="block font-mono text-xl font-bold">{s.v}</span>
                <span className="mt-1 block text-[9px] uppercase text-muted-foreground">{s.l}</span>
              </div>
            ))}
          </div>

          <div className="mb-2 text-[10px] font-semibold text-muted-foreground">
            {t('step2.generatedAgentPersonas')}
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {profiles.map((profile, idx) => (
              <div
                key={idx}
                onClick={() => onSelectProfile(profile)}
                className="cursor-pointer rounded-md border bg-card p-3 transition hover:border-[#FF5722]"
              >
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-semibold">{profile.username || 'Unknown'}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    @{profile.name || `agent_${idx}`}
                  </span>
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {profile.profession || t('step2.unknownProfession')}
                </div>
                <p className="mt-1 line-clamp-2 text-[11px] text-foreground/70">
                  {profile.bio || t('step2.noBio')}
                </p>
                {!!profile.interested_topics?.length && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {profile.interested_topics.slice(0, 3).map((topic) => (
                      <span key={topic} className="rounded bg-muted px-1.5 py-0.5 text-[10px]">
                        {topic}
                      </span>
                    ))}
                    {profile.interested_topics.length > 3 && (
                      <span className="px-1 text-[10px] text-muted-foreground">
                        +{profile.interested_topics.length - 3}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </StepCard>
  )
}
