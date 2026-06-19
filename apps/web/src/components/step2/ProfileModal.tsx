import { useTranslation } from 'react-i18next'

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import type { Profile } from '@/lib/step2-types'

interface Props {
  profile: Profile | null
  onClose: () => void
}

/** 人设四维度框架（静态展示，对应后端单一 persona 文本的结构化注解）。 */
const PERSONA_DIMENSIONS = [
  { titleKey: 'step2.personaDimExperience', descKey: 'step2.personaDimExperienceDesc' },
  { titleKey: 'step2.personaDimBehavior', descKey: 'step2.personaDimBehaviorDesc' },
  { titleKey: 'step2.personaDimMemory', descKey: 'step2.personaDimMemoryDesc' },
  { titleKey: 'step2.personaDimSocial', descKey: 'step2.personaDimSocialDesc' },
] as const

/** Agent 人设详情模态框（基于 shadcn Dialog）。 */
export function ProfileModal({ profile, onClose }: Props) {
  const { t } = useTranslation()

  const genderMap: Record<string, string> = {
    male: t('step2.genderMale'),
    female: t('step2.genderFemale'),
    other: t('step2.genderOther'),
  }

  return (
    <Dialog open={!!profile} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        {profile && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-baseline gap-2">
                {profile.username}
                <span className="text-muted-foreground font-mono text-xs font-normal">
                  @{profile.name}
                </span>
              </DialogTitle>
              <span className="text-muted-foreground text-xs">{profile.profession}</span>
            </DialogHeader>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Info
                label={t('step2.profileModalAge')}
                value={`${profile.age ?? '-'} ${t('step2.yearsOld')}`}
              />
              <Info
                label={t('step2.profileModalGender')}
                value={genderMap[profile.gender ?? ''] || profile.gender || '-'}
              />
              <Info label={t('step2.profileModalCountry')} value={profile.country || '-'} />
              <Info label={t('step2.profileModalMbti')} value={profile.mbti || '-'} />
            </div>

            <Section label={t('step2.profileModalBio')}>
              <p className="text-foreground/80 text-xs leading-relaxed">
                {profile.bio || t('step2.noBio')}
              </p>
            </Section>

            {!!profile.interested_topics?.length && (
              <Section label={t('step2.profileModalTopics')}>
                <div className="flex flex-wrap gap-1.5">
                  {profile.interested_topics.map((topic) => (
                    <Badge key={topic} variant="secondary">
                      {topic}
                    </Badge>
                  ))}
                </div>
              </Section>
            )}

            {profile.persona && (
              <Section label={t('step2.profileModalPersona')}>
                {/* 人设维度框架：Experience / Behavior / Memory / Social */}
                <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {PERSONA_DIMENSIONS.map((dim) => (
                    <div key={dim.titleKey} className="bg-muted/40 rounded-md border p-2">
                      <span className="block text-[11px] font-semibold">{t(dim.titleKey)}</span>
                      <span className="text-muted-foreground mt-0.5 block text-[10px] leading-snug">
                        {t(dim.descKey)}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="bg-muted/50 text-foreground/80 whitespace-pre-wrap rounded-md p-3 text-[11px] leading-relaxed">
                  {profile.persona}
                </p>
              </Section>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted-foreground block text-[10px]">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="text-muted-foreground mb-2 block text-[10px] font-semibold">{label}</span>
      {children}
    </div>
  )
}
