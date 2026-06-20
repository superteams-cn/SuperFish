import { useTranslation } from 'react-i18next'
import { Check } from 'lucide-react'

import { PlatformLogo } from '@/components/step3/PlatformLogo'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { STATUS_TEXT } from '@/lib/ui-meta'

interface Props {
  name: string
  /** 平台标识，用于展示真实 Logo */
  platform?: string
  running?: boolean
  completed?: boolean
  currentRound: number
  totalRounds: number | string
  elapsedTime: string
  actionsCount: number
  /** 可用动作提示列表 */
  availableActions: string[]
}

/** 单平台运行状态卡片（轮次 / 模拟时长 / 动作数 + 可用动作 tooltip）。 */
export function PlatformStatusCard({
  name,
  platform,
  running,
  completed,
  currentRound,
  totalRounds,
  elapsedTime,
  actionsCount,
  availableActions,
}: Props) {
  const { t } = useTranslation()

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            'relative flex-1 cursor-default rounded-md border p-3 transition',
            running && 'border-brand',
            completed && 'border-green-500',
          )}
        >
          <div className="mb-2 flex items-center gap-2">
            <PlatformLogo platform={platform} className="h-3.5 w-3.5" />
            <span className="text-xs font-semibold">{name}</span>
            {completed && <Check className={cn('h-3.5 w-3.5', STATUS_TEXT.success)} />}
            {running && <span className="bg-brand h-1.5 w-1.5 animate-pulse rounded-full" />}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <Stat label={t('step3.statRound')} value={`${currentRound}/${totalRounds}`} />
            <Stat label={t('step3.statTime')} value={elapsedTime} />
            <Stat label={t('step3.statActs')} value={String(actionsCount)} />
          </div>
        </div>
      </TooltipTrigger>
      <TooltipContent className="max-w-[240px]" side="bottom" align="start">
        <p className="text-muted-foreground/80 mb-1.5 text-[10px] font-semibold uppercase tracking-wide">
          {t('step3.availableActions')}
        </p>
        <div className="flex flex-wrap gap-1">
          {availableActions.map((a) => (
            <span
              key={a}
              className="bg-primary-foreground/15 rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide"
            >
              {a}
            </span>
          ))}
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted-foreground block text-[9px] uppercase">{label}</span>
      <span className="font-mono text-sm font-semibold">{value}</span>
    </div>
  )
}
