import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'
import { ACCENT_SOFT, platformMeta, type AccentName } from '@/lib/ui-meta'

/**
 * 柔和徽章：浅底 + 同色文字的小标签（话题 / 平台 / 工具分类）。
 *
 * 区别于 `ui/badge.tsx`（实底强调徽章）：SoftBadge 走 `lib/ui-meta.ts` 的
 * 集中色板，业务层不再手写 `bg-x-500/15 text-x-600` 这类字符串。
 *
 * - 不传 accent/platform → 中性灰底（等价旧 `bg-secondary` 话题 chip）。
 * - 传 accent → 取 ACCENT_SOFT 同色板（violet/blue/green/orange/cyan/pink）。
 * - 传 platform → 取 PLATFORM_META.badge（twitter / reddit 双轨）。
 */
const softBadgeVariants = cva(
  'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium',
  {
    variants: {
      tone: {
        neutral: 'bg-secondary text-secondary-foreground',
      },
    },
    defaultVariants: {
      tone: 'neutral',
    },
  },
)

export interface SoftBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof softBadgeVariants> {
  /** 工具/分类强调色（取自 ui-meta 的 ACCENT_SOFT）。 */
  accent?: AccentName
  /** 平台徽章（取自 ui-meta 的 PLATFORM_META.badge）。 */
  platform?: string | null
}

const SoftBadge = React.forwardRef<HTMLSpanElement, SoftBadgeProps>(
  ({ className, accent, platform, tone, ...props }, ref) => {
    const colorClass = platform
      ? platformMeta(platform).badge
      : accent
        ? ACCENT_SOFT[accent]
        : undefined
    // 有具体色板时不叠加中性底色，避免双背景。
    return (
      <span
        ref={ref}
        className={cn(
          softBadgeVariants({ tone: colorClass ? undefined : tone }),
          colorClass,
          className,
        )}
        {...props}
      />
    )
  },
)
SoftBadge.displayName = 'SoftBadge'

export { SoftBadge, softBadgeVariants }
