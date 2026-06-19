import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type CardStatus = 'pending' | 'processing' | 'completed'

interface StepCardProps {
  num: string
  title: string
  status: CardStatus
  /** 状态徽标文案；为空则不显示徽标 */
  statusText?: string
  /** 是否高亮（当前进行中） */
  active?: boolean
  apiNote?: string
  description?: string
  children?: ReactNode
}

/** 各步骤卡片的统一外壳（编号 + 标题 + 状态徽标 + 内容）。Step1/Step2 共用。 */
export function StepCard({
  num,
  title,
  status,
  statusText,
  active,
  apiNote,
  description,
  children,
}: StepCardProps) {
  const badgeCls =
    status === 'completed'
      ? 'bg-green-100 text-green-700'
      : status === 'processing'
        ? 'bg-[#FF5722] text-white'
        : 'bg-muted text-muted-foreground'

  return (
    <div
      className={cn(
        'bg-card relative rounded-lg border p-5 shadow-sm transition',
        active && 'border-[#FF5722] shadow-md',
      )}
    >
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-muted-foreground font-mono text-xl font-bold">{num}</span>
          <span className="text-sm font-semibold">{title}</span>
        </div>
        {statusText && (
          <span className={cn('rounded px-2 py-1 text-[10px] font-semibold uppercase', badgeCls)}>
            {statusText}
          </span>
        )}
      </div>
      {apiNote && <p className="text-muted-foreground mb-2 font-mono text-[10px]">{apiNote}</p>}
      {description && (
        <p className="text-muted-foreground mb-4 text-xs leading-relaxed">{description}</p>
      )}
      {children}
    </div>
  )
}
