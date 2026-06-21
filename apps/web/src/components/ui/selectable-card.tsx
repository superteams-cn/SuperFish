import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

/**
 * 可点击卡片：以 `<button>` 承载的卡片表面（人物卡 / 选人瓦片 / 选项瓦片等）。
 *
 * 收口各处手写的「卡片面 + hover 上浮 + 焦点环」可点击容器，统一交互与无障碍：
 * - surface：card（令牌面 bg-card+border）/ glass（复用 .glass）/ plain（自定义底，交给 className）
 * - lift：是否 hover 上浮（选中态通常关掉）
 * 圆角 / 内边距 / 内部布局仍由调用方经 className 决定（各处尺寸不同）。
 *
 * 注意：内部含其它 `<button>`（如卡内删除按钮）的卡片不可用本组件——
 * button 不能嵌套 button，应保留 `<div role="button">`。
 */
const selectableCardVariants = cva(
  'group relative text-left transition-transform duration-300 focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      surface: {
        card: 'bg-card border',
        glass: 'glass',
        plain: '',
      },
      lift: {
        true: 'hover:-translate-y-0.5',
        false: '',
      },
    },
    defaultVariants: {
      surface: 'card',
      lift: true,
    },
  },
)

export interface SelectableCardProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof selectableCardVariants> {}

const SelectableCard = React.forwardRef<HTMLButtonElement, SelectableCardProps>(
  ({ className, surface, lift, type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(selectableCardVariants({ surface, lift }), className)}
      {...props}
    />
  ),
)
SelectableCard.displayName = 'SelectableCard'

export { SelectableCard, selectableCardVariants }
