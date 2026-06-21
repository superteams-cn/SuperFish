import * as React from 'react'
import { ChevronDown } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 「点击展开」头部：圆角虚线框 + 左侧图标/标题/提示 + 右侧 ChevronDown 旋转。
 *
 * 仅负责头部本身（受控按钮 + 箭头方向）；展开内容仍由调用方按
 * `{open && <内容/>}` 渲染，不接管展开状态，保持各 Step 现有逻辑不变。
 */
export interface CollapsibleHeaderProps extends Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  'onToggle'
> {
  open: boolean
  onToggle: () => void
  /** 左侧图标（如 lucide 的 <Code className="h-4 w-4" />）。 */
  icon?: React.ReactNode
  label: React.ReactNode
  /** 次要提示文字，sm 以上才显示（前置「· 」分隔）。 */
  hint?: React.ReactNode
}

const CollapsibleHeader = React.forwardRef<HTMLButtonElement, CollapsibleHeaderProps>(
  ({ open, onToggle, icon, label, hint, className, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={cn(
        'text-muted-foreground hover:text-foreground flex w-full items-center justify-between rounded-xl border border-dashed px-4 py-3 text-sm transition-colors',
        className,
      )}
      {...props}
    >
      <span className="flex items-center gap-2">
        {icon}
        {label}
        {hint && (
          <span className="text-muted-foreground/70 hidden text-xs sm:inline">· {hint}</span>
        )}
      </span>
      <ChevronDown className={cn('h-4 w-4 transition-transform', open && 'rotate-180')} />
    </button>
  ),
)
CollapsibleHeader.displayName = 'CollapsibleHeader'

export { CollapsibleHeader }
