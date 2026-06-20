import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Loader2 } from 'lucide-react'

import { Markdown } from '@/components/Markdown'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { ReportOutline } from '@/lib/step4-types'

interface Props {
  outline: ReportOutline | null
  /** 已生成章节内容：{ sectionIndex(1基): content } */
  generatedSections: Record<number, string>
  currentSectionIndex: number | null
}

/** 报告面板：标题 + 章节列表（已完成章节渲染 markdown，可折叠）。 */
export function ReportOutlinePanel({ outline, generatedSections, currentSectionIndex }: Props) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())

  const toggle = (idx: number) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  if (!outline) {
    // 大纲未就绪时用骨架屏占位，比单一 spinner 更贴近最终布局
    return (
      <div className="mx-auto w-full max-w-6xl space-y-4">
        <div className="text-muted-foreground flex items-center gap-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('step4.generatingReport')}
        </div>
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-full" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-2 rounded-lg border p-4">
            <Skeleton className="h-5 w-1/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      {/* 报告头部 */}
      <div className="mb-6 border-b pb-4">
        <h1 className="text-2xl font-bold tracking-tight">{outline.title}</h1>
        {outline.summary && <p className="text-muted-foreground mt-2 text-sm">{outline.summary}</p>}
      </div>

      {/* 章节列表 */}
      <div className="space-y-4">
        {outline.sections?.map((section, idx) => {
          const sectionNo = idx + 1
          const content = generatedSections[sectionNo]
          const isActive = currentSectionIndex === sectionNo
          const isCollapsed = collapsed.has(idx)
          return (
            <div
              key={idx}
              className={cn(
                'rounded-lg border p-4',
                isActive && 'border-brand',
                content && 'cursor-default',
              )}
            >
              <div
                className={cn('flex items-center gap-2', content && 'cursor-pointer')}
                role={content ? 'button' : undefined}
                tabIndex={content ? 0 : undefined}
                onClick={() => content && toggle(idx)}
                onKeyDown={(e) => {
                  if (content && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault()
                    toggle(idx)
                  }
                }}
              >
                <span className="text-muted-foreground font-mono text-sm font-bold">
                  {String(sectionNo).padStart(2, '0')}
                </span>
                <h3 className="flex-1 text-base font-semibold">{section.title}</h3>
                {content && (
                  <ChevronDown
                    className={cn('h-4 w-4 transition-transform', isCollapsed && '-rotate-90')}
                  />
                )}
              </div>

              {!isCollapsed && (
                <div className="mt-3">
                  {content ? (
                    <Markdown content={content} stripLeadingH2 />
                  ) : isActive ? (
                    <div className="text-brand flex items-center gap-2 text-xs">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      {t('step4.generatingSection', { title: section.title })}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
