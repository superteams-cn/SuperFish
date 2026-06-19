import { useTranslation } from 'react-i18next'
import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'

interface Props {
  name: string
  running?: boolean
  completed?: boolean
  currentRound: number
  totalRounds: number | string
  elapsedTime: string
  actionsCount: number
  /** 可用动作提示列表 */
  availableActions: string[]
}

/** 单平台运行状态卡片（轮次 / 模拟时长 / 动作数 + 可用动作提示）。 */
export function PlatformStatusCard({
  name,
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
    <div
      className={cn(
        'group relative flex-1 rounded-md border p-3 transition',
        running && 'border-[#FF5722]',
        completed && 'border-green-500',
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-semibold">{name}</span>
        {completed && <Check className="h-3.5 w-3.5 text-green-600" />}
        {running && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#FF5722]" />}
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <Stat label={t('step3.statRound')} value={`${currentRound}/${totalRounds}`} />
        <Stat label={t('step3.statTime')} value={elapsedTime} />
        <Stat label={t('step3.statActs')} value={String(actionsCount)} />
      </div>
      {/* 可用动作提示 */}
      <div className="mt-2 hidden flex-wrap gap-1 group-hover:flex">
        {availableActions.map((a) => (
          <span key={a} className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[9px]">
            {a}
          </span>
        ))}
      </div>
    </div>
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
