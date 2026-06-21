import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * 空态：居中图标 + 标题 + 说明 + 可选操作区。
 * 统一走 `text-muted-foreground` 语义色，替代各处手写的空态块。
 */
export interface EmptyStateProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  icon?: React.ReactNode
  title: React.ReactNode
  description?: React.ReactNode
  /** 操作区（按钮等），渲染在说明下方。 */
  action?: React.ReactNode
}

const EmptyState = React.forwardRef<HTMLDivElement, EmptyStateProps>(
  ({ icon, title, description, action, className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex flex-col items-center justify-center gap-2 px-6 py-12 text-center',
        className,
      )}
      {...props}
    >
      {icon && <div className="text-muted-foreground/60 [&_svg]:h-8 [&_svg]:w-8">{icon}</div>}
      <p className="text-foreground text-sm font-medium">{title}</p>
      {description && <p className="text-muted-foreground max-w-sm text-xs">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  ),
)
EmptyState.displayName = 'EmptyState'

export { EmptyState }
