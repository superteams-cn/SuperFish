import { useTranslation } from 'react-i18next'
import { FolderOpen } from 'lucide-react'

import { useProjectQuota } from '@/hooks/useProjectQuota'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface Props {
  /** 未登录等场景置 false：不拉取也不展示 */
  enabled?: boolean
  className?: string
}

/**
 * 顶栏长驻的项目名额胶囊：展示「已用/上限」，满时变红，悬浮说明。
 * 与并发推演名额胶囊（QuotaChip）同形，自包含拉取（30s 轮询保鲜）。
 */
export function ProjectQuotaChip({ enabled = true, className }: Props) {
  const { t } = useTranslation()
  const { quota } = useProjectQuota({ enabled, pollMs: 30000 })

  if (!quota) return null
  const full = quota.used >= quota.limit

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              'inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full px-3 text-xs font-medium shadow-sm backdrop-blur',
              full
                ? 'bg-destructive/15 text-destructive'
                : 'bg-secondary text-secondary-foreground',
              className,
            )}
          >
            <FolderOpen className="h-4 w-4" />
            {t('main.projectQuotaChip', { used: quota.used, limit: quota.limit })}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs">
          {t('main.projectQuotaHint', { limit: quota.limit })}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
