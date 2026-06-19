import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type CardStatus = 'pending' | 'processing' | 'completed'

interface StepCardProps {
  num: string
  title: string
  status: CardStatus
  /** 状态徽标文案 */
  statusText: string
  /** 是否高亮（当前进行中） */
  active?: boolean
  apiNote?: string
  description?: string
  children?: ReactNode
}

/** Step2 各步骤卡片的统一外壳（编号 + 标题 + 状态徽标 + 内容）。 */
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
        'relative rounded-lg border bg-card p-5 shadow-sm transition',
        active && 'border-[#FF5722] shadow-md',
      )}
    >
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xl font-bold text-muted-foreground">{num}</span>
          <span className="text-sm font-semibold">{title}</span>
        </div>
        <span className={cn('rounded px-2 py-1 text-[10px] font-semibold uppercase', badgeCls)}>
          {statusText}
        </span>
      </div>
      {apiNote && <p className="mb-2 font-mono text-[10px] text-muted-foreground">{apiNote}</p>}
      {description && (
        <p className="mb-4 text-xs leading-relaxed text-muted-foreground">{description}</p>
      )}
      {children}
    </div>
  )
}
