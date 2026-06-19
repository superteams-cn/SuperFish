import { useTranslation } from 'react-i18next'

import { StepCard } from '@/components/StepCard'
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
          <div className="bg-muted/50 mb-4 grid grid-cols-3 gap-3 rounded-md p-4">
            {[
              { v: profiles.length, l: t('step2.currentAgentCount') },
              { v: expectedTotal || '-', l: t('step2.expectedAgentTotal') },
              { v: totalTopics, l: t('step2.relatedTopicsCount') },
            ].map((s, i) => (
              <div key={i} className="text-center">
                <span className="block font-mono text-xl font-bold">{s.v}</span>
                <span className="text-muted-foreground mt-1 block text-[9px] uppercase">{s.l}</span>
              </div>
            ))}
          </div>

          <div className="text-muted-foreground mb-2 text-[10px] font-semibold">
            {t('step2.generatedAgentPersonas')}
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {profiles.map((profile, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => onSelectProfile(profile)}
                className="bg-card cursor-pointer rounded-md border p-3 text-left transition hover:border-[#FF5722]"
              >
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-semibold">{profile.username || 'Unknown'}</span>
                  <span className="text-muted-foreground font-mono text-[10px]">
                    @{profile.name || `agent_${idx}`}
                  </span>
                </div>
                <div className="text-muted-foreground mt-0.5 text-[11px]">
                  {profile.profession || t('step2.unknownProfession')}
                </div>
                <p className="text-foreground/70 mt-1 line-clamp-2 text-[11px]">
                  {profile.bio || t('step2.noBio')}
                </p>
                {!!profile.interested_topics?.length && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {profile.interested_topics.slice(0, 3).map((topic) => (
                      <span key={topic} className="bg-muted rounded px-1.5 py-0.5 text-[10px]">
                        {topic}
                      </span>
                    ))}
                    {profile.interested_topics.length > 3 && (
                      <span className="text-muted-foreground px-1 text-[10px]">
                        +{profile.interested_topics.length - 3}
                      </span>
                    )}
                  </div>
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </StepCard>
  )
}
