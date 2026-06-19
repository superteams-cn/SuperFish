import { cn } from '@/lib/utils'

export type StatusVariant = 'processing' | 'completed' | 'error' | 'idle'

const COLORS: Record<StatusVariant, string> = {
  processing: 'bg-[#FF5722] animate-pulse',
  completed: 'bg-green-500',
  error: 'bg-red-500',
  idle: 'bg-muted-foreground/40',
}

/** 状态指示圆点（处理中会脉冲动画）。 */
export function StatusDot({ variant, className }: { variant: StatusVariant; className?: string }) {
  return <span className={cn('h-2 w-2 rounded-full', COLORS[variant], className)} />
}
