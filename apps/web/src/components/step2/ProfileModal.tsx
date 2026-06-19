import { useTranslation } from 'react-i18next'

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import type { Profile } from '@/lib/step2-types'

interface Props {
  profile: Profile | null
  onClose: () => void
}

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
                <span className="font-mono text-xs font-normal text-muted-foreground">@{profile.name}</span>
              </DialogTitle>
              <span className="text-xs text-muted-foreground">{profile.profession}</span>
            </DialogHeader>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Info label={t('step2.profileModalAge')} value={`${profile.age ?? '-'} ${t('step2.yearsOld')}`} />
              <Info label={t('step2.profileModalGender')} value={genderMap[profile.gender ?? ''] || profile.gender || '-'} />
              <Info label={t('step2.profileModalCountry')} value={profile.country || '-'} />
              <Info label={t('step2.profileModalMbti')} value={profile.mbti || '-'} />
            </div>

            <Section label={t('step2.profileModalBio')}>
              <p className="text-xs leading-relaxed text-foreground/80">{profile.bio || t('step2.noBio')}</p>
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
                <p className="whitespace-pre-wrap rounded-md bg-muted/50 p-3 text-[11px] leading-relaxed text-foreground/80">
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
      <span className="block text-[10px] text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}
