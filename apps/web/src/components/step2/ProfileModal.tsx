import { useTranslation } from 'react-i18next'

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import type { PersonaDimensions, Profile } from '@/lib/step2-types'

interface Props {
  profile: Profile | null
  onClose: () => void
}

/**
 * 人设四维度框架。
 * `key` 对应后端 dimensions 对象字段；有真实内容时展示真实内容，
 * 否则回退到 descKey 注解式展示（向后兼容旧版单一 persona 文本）。
 */
const PERSONA_DIMENSIONS = [
  {
    key: 'experience',
    titleKey: 'step2.personaDimExperience',
    descKey: 'step2.personaDimExperienceDesc',
  },
  {
    key: 'behavior',
    titleKey: 'step2.personaDimBehavior',
    descKey: 'step2.personaDimBehaviorDesc',
  },
  { key: 'memory', titleKey: 'step2.personaDimMemory', descKey: 'step2.personaDimMemoryDesc' },
  { key: 'social', titleKey: 'step2.personaDimSocial', descKey: 'step2.personaDimSocialDesc' },
] as const satisfies ReadonlyArray<{
  key: keyof PersonaDimensions
  titleKey: string
  descKey: string
}>

/** Agent 人设详情模态框（基于 shadcn Dialog）。 */
export function ProfileModal({ profile, onClose }: Props) {
  const { t } = useTranslation()

  const genderMap: Record<string, string> = {
    male: t('step2.genderMale'),
    female: t('step2.genderFemale'),
    other: t('step2.genderOther'),
  }

  // 是否存在后端产出的真实四维度内容（任一维度非空即视为有）
  const hasDimensions = PERSONA_DIMENSIONS.some((dim) => profile?.dimensions?.[dim.key]?.trim())

  return (
    <Dialog open={!!profile} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        {profile && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-baseline gap-2">
                {profile.name || profile.username}
                <span className="text-muted-foreground font-mono text-xs font-normal">
                  @{profile.username}
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

            {hasDimensions ? (
              /* 真实四维度内容：后端 dimensions 字段产出 */
              <Section label={t('step2.profileModalPersona')}>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {PERSONA_DIMENSIONS.map((dim) => {
                    const content = profile.dimensions?.[dim.key]?.trim()
                    return (
                      <div key={dim.key} className="bg-muted/40 rounded-md border p-2.5">
                        <span className="block text-[11px] font-semibold">{t(dim.titleKey)}</span>
                        <p className="text-foreground/80 mt-1 whitespace-pre-wrap text-[11px] leading-relaxed">
                          {content || t('step2.personaDimEmpty')}
                        </p>
                      </div>
                    )
                  })}
                </div>
              </Section>
            ) : (
              profile.persona && (
                <Section label={t('step2.profileModalPersona')}>
                  {/* 向后兼容：无 dimensions 时回退到注解式四维框架 + 单一 persona 文本 */}
                  <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {PERSONA_DIMENSIONS.map((dim) => (
                      <div key={dim.key} className="bg-muted/40 rounded-md border p-2">
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
              )
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
