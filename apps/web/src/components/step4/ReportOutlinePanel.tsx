import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Loader2 } from 'lucide-react'

import { Markdown } from '@/components/Markdown'
import { cn } from '@/lib/utils'
import type { ReportOutline } from '@/lib/step4-types'

interface Props {
  reportId: string
  outline: ReportOutline | null
  /** 已生成章节内容：{ sectionIndex(1基): content } */
  generatedSections: Record<number, string>
  currentSectionIndex: number | null
}

/** 报告左侧面板：标题 + 章节列表（已完成章节渲染 markdown，可折叠）。 */
export function ReportOutlinePanel({
  reportId,
  outline,
  generatedSections,
  currentSectionIndex,
}: Props) {
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
    return (
      <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-3 text-sm">
        <Loader2 className="h-6 w-6 animate-spin" />
        {t('step4.generatingReport', { defaultValue: '报告生成中…' })}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl">
      {/* 报告头部 */}
      <div className="mb-6 border-b pb-4">
        <div className="text-muted-foreground mb-2 flex items-center gap-3 text-[10px]">
          <span className="rounded bg-[#FF5722] px-2 py-0.5 font-semibold text-white">
            {t('step4.predictionReport')}
          </span>
          <span className="font-mono">ID: {reportId}</span>
        </div>
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
                isActive && 'border-[#FF5722]',
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
                    <div className="flex items-center gap-2 text-xs text-[#FF5722]">
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
