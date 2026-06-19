import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

import type { Profile } from '@/lib/step2-types'

interface Props {
  profile: Profile | null
  onClose: () => void
}

/** Agent 人设详情模态框。 */
export function ProfileModal({ profile, onClose }: Props) {
  const { t } = useTranslation()
  if (!profile) return null

  const genderMap: Record<string, string> = {
    male: t('step2.genderMale'),
    female: t('step2.genderFemale'),
    other: t('step2.genderOther'),
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="max-h-[85vh] w-full max-w-lg overflow-hidden rounded-lg border bg-background shadow-xl">
        <div className="flex items-center justify-between border-b bg-muted/50 px-5 py-4">
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-base font-bold">{profile.username}</span>
              <span className="font-mono text-xs text-muted-foreground">@{profile.name}</span>
            </div>
            <span className="text-xs text-muted-foreground">{profile.profession}</span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[calc(85vh-72px)] overflow-y-auto p-5">
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Info label={t('step2.profileModalAge')} value={`${profile.age ?? '-'} ${t('step2.yearsOld')}`} />
            <Info label={t('step2.profileModalGender')} value={genderMap[profile.gender ?? ''] || profile.gender || '-'} />
            <Info label={t('step2.profileModalCountry')} value={profile.country || '-'} />
            <Info label={t('step2.profileModalMbti')} value={profile.mbti || '-'} />
          </div>

          <Section label={t('step2.profileModalBio')}>
            <p className="text-xs leading-relaxed text-foreground/80">
              {profile.bio || t('step2.noBio')}
            </p>
          </Section>

          {!!profile.interested_topics?.length && (
            <Section label={t('step2.profileModalTopics')}>
              <div className="flex flex-wrap gap-1.5">
                {profile.interested_topics.map((topic) => (
                  <span key={topic} className="rounded bg-muted px-2 py-0.5 text-[11px]">
                    {topic}
                  </span>
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
        </div>
      </div>
    </div>
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
    <div className="mb-4">
      <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}
