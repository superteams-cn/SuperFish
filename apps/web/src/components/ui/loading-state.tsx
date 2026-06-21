import * as React from 'react'
import { Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 统一加载态：居中旋转图标 + 可选文案。
 * 收口各处零散的 `Loader2 ... animate-spin` 写法，保证尺寸/间距/语义色一致。
 */
export interface LoadingStateProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 加载文案；省略则只显示图标。 */
  label?: React.ReactNode
  /** 图标尺寸（Tailwind 类），默认 h-5 w-5。 */
  iconClassName?: string
}

const LoadingState = React.forwardRef<HTMLDivElement, LoadingStateProps>(
  ({ label, iconClassName, className, ...props }, ref) => (
    <div
      ref={ref}
      role="status"
      className={cn(
        'text-muted-foreground flex flex-col items-center justify-center gap-2 px-6 py-12 text-sm',
        className,
      )}
      {...props}
    >
      <Loader2 className={cn('animate-spin', iconClassName ?? 'h-5 w-5')} />
      {label && <span>{label}</span>}
    </div>
  ),
)
LoadingState.displayName = 'LoadingState'

export { LoadingState }
