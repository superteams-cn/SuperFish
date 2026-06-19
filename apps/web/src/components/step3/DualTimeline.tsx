import { useTranslation } from 'react-i18next'

import { ActionCard } from '@/components/step3/ActionCard'
import { cn } from '@/lib/utils'
import type { ActionItem } from '@/lib/step3-types'

interface Props {
  actions: ActionItem[]
}

/**
 * 双轨动作时间线：中轴线左侧为信息广场(twitter)、右侧为话题社区(reddit)，
 * 按时间交替排布，平台区分鲜明。窄屏（< md）自动降级为单轨列表。
 */
export function DualTimeline({ actions }: Props) {
  const { t } = useTranslation()

  return (
    <>
      {/* 窄屏：单轨列表 */}
      <div className="border-muted space-y-2 border-l pl-1 md:hidden">
        {actions.map((action) => (
          <ActionCard key={action._uniqueId || action.id} action={action} variant="list" />
        ))}
      </div>

      {/* 宽屏：双轨时间线 */}
      <div className="mx-auto hidden max-w-4xl md:block">
        {/* 轨道分栏表头 */}
        <div className="text-muted-foreground mb-3 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide opacity-70">
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-sky-500" />
            {t('step3.platformTwitterName')}
          </span>
          <span className="flex items-center gap-1">
            {t('step3.platformRedditName')}
            <span className="h-1.5 w-1.5 rounded-full bg-orange-500" />
          </span>
        </div>
        <div className="relative">
          {/* 中轴线 */}
          <div className="bg-border absolute bottom-0 left-1/2 top-0 w-px -translate-x-1/2" />
          <div className="space-y-5">
            {actions.map((action) => {
              const isTwitter = action.platform === 'twitter'
              return (
                <div
                  key={action._uniqueId || action.id}
                  className={cn('relative flex', isTwitter ? 'justify-start' : 'justify-end')}
                >
                  {/* 中轴标记点 */}
                  <span
                    className={cn(
                      'border-background absolute left-1/2 top-3 z-[1] h-3 w-3 -translate-x-1/2 rounded-full border-2',
                      isTwitter ? 'bg-sky-500' : 'bg-orange-500',
                    )}
                  />
                  <div className={cn('w-[calc(50%-1.5rem)]', isTwitter ? 'pr-2' : 'pl-2')}>
                    <ActionCard action={action} variant="bare" />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </>
  )
}
