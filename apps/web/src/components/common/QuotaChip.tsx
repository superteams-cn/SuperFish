import { useTranslation } from 'react-i18next'
import { Clapperboard } from 'lucide-react'

import { useSimulationQuota } from '@/hooks/useSimulationQuota'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface QuotaChipProps {
  /** 未登录等场景置 false：不拉取也不展示 */
  enabled?: boolean
  className?: string
}

/**
 * 顶栏长驻的并发推演名额胶囊：展示「在跑/上限」，满时变红，悬浮说明原因。
 *
 * 自包含拉取（含 30s 轮询保持新鲜），可直接放进任意页面顶栏。拉取失败/未登录则不渲染。
 */
export function QuotaChip({ enabled = true, className }: QuotaChipProps) {
  const { t } = useTranslation()
  const { quota } = useSimulationQuota({ enabled, pollMs: 30000 })

  if (!quota) return null
  const full = quota.running >= quota.limit

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* 与相邻的「记录 / 主题 / 语言」对齐：secondary + sm + rounded-full */}
          <span
            className={cn(
              'inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full px-3 text-xs font-medium shadow-sm backdrop-blur',
              full
                ? 'bg-destructive/15 text-destructive'
                : 'bg-secondary text-secondary-foreground',
              className,
            )}
          >
            <Clapperboard className="h-4 w-4" />
            {t('main.quotaChip', { running: quota.running, limit: quota.limit })}
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs">
          {t('main.quotaHint', { limit: quota.limit })}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
