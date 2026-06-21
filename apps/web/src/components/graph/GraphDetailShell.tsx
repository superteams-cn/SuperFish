import type { ReactNode } from 'react'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 图谱详情面板外壳：右上浮层，标题 + 可选类型徽章 + 关闭按钮 + 滚动内容区。
 * 图谱面板复用；z-index 由 className 覆盖。
 */
export function GraphDetailShell({
  title,
  badge,
  onClose,
  className,
  children,
}: {
  title: string
  badge?: { label: string; color: string }
  onClose: () => void
  className?: string
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'bg-background absolute right-3 top-16 z-20 flex max-h-[calc(100%-5rem)] w-80 flex-col rounded-lg border shadow-xl',
        className,
      )}
    >
      <div className="bg-muted/40 flex items-center justify-between gap-2 border-b px-4 py-3">
        <span className="text-sm font-semibold">{title}</span>
        <div className="flex items-center gap-2">
          {badge && (
            <span
              className="rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
              style={{ backgroundColor: badge.color }}
            >
              {badge.label}
            </span>
          )}
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 text-sm">{children}</div>
    </div>
  )
}
