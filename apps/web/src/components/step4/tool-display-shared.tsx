import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { NamedEntity, RelationLink } from '@/lib/step4-types'

/** 把字符数格式化为 "1.2k chars" / "320 chars"。 */
function formatSize(length?: number): string {
  if (!length) return ''
  if (length >= 1000) return `${(length / 1000).toFixed(1)}k chars`
  return `${length} chars`
}

/** 工具结果通用外壳：标题 + 统计指标 + 可选查询行。 */
export function ToolResultShell({
  title,
  stats,
  resultLength,
  query,
  queryLabel,
  children,
}: {
  title: string
  stats: { label: string; value: number | string }[]
  resultLength?: number
  query?: string
  queryLabel?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-xs font-semibold">{title}</span>
        <div className="text-muted-foreground flex items-center gap-1.5 font-mono text-[10px]">
          {stats.map((s, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <span className="opacity-40">/</span>}
              <span className="text-foreground font-semibold">{s.value}</span>
              <span>{s.label}</span>
            </span>
          ))}
          {resultLength ? (
            <>
              <span className="opacity-40">·</span>
              <span>{formatSize(resultLength)}</span>
            </>
          ) : null}
        </div>
      </div>
      {query ? (
        <p className="text-muted-foreground text-[11px] leading-snug">
          {queryLabel && <span className="font-medium">{queryLabel}</span>}
          {query}
        </p>
      ) : null}
      {children}
    </div>
  )
}

/** 轻量内联 Tab 切换条（不依赖 Radix Tabs，便于多实例并存于时间线内）。 */
export function MiniTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string }[]
  active: string
  onChange: (key: string) => void
}) {
  return (
    <div className="bg-muted/60 inline-flex flex-wrap gap-1 rounded-md p-0.5">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={() => onChange(tab.key)}
          className={cn(
            'rounded px-2 py-0.5 text-[11px] transition-colors',
            active === tab.key
              ? 'bg-background text-foreground font-medium shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

/** 编号事实列表（带"展开全部/收起"）。 */
export function FactList({ facts, initial = 5 }: { facts: string[]; initial?: number }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? facts : facts.slice(0, initial)
  return (
    <div className="space-y-1.5">
      {shown.map((fact, i) => (
        <div key={i} className="flex gap-2 text-[11px] leading-snug">
          <span className="text-muted-foreground shrink-0 font-mono">{i + 1}.</span>
          <span>{fact}</span>
        </div>
      ))}
      {facts.length > initial && (
        <Button
          variant="link"
          size="sm"
          className="text-brand h-auto p-0 text-[10px]"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? t('step4.collapse') : t('step4.expandAll', { count: facts.length })}
        </Button>
      )}
    </div>
  )
}

/** 实体标签网格（带"展开全部/收起"）。 */
export function EntityGrid({
  entities,
  initial = 12,
}: {
  entities: NamedEntity[]
  initial?: number
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? entities : entities.slice(0, initial)
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {shown.map((e, i) => (
          <span
            key={i}
            title={e.summary || undefined}
            className="bg-muted inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]"
          >
            <span className="font-medium">{e.name}</span>
            {e.type && <span className="text-muted-foreground">{e.type}</span>}
            {e.relatedFactsCount ? (
              <span className="text-brand">
                {t('step4.factCount', { count: e.relatedFactsCount })}
              </span>
            ) : null}
          </span>
        ))}
      </div>
      {entities.length > initial && (
        <Button
          variant="link"
          size="sm"
          className="text-brand h-auto p-0 text-[10px]"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded
            ? t('step4.collapse')
            : t('step4.expandAllEntities', { count: entities.length })}
        </Button>
      )}
    </div>
  )
}

/** 关系链列表（A —rel→ B）。 */
export function RelationList({
  relations,
  initial = 5,
}: {
  relations: RelationLink[]
  initial?: number
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? relations : relations.slice(0, initial)
  return (
    <div className="space-y-1.5">
      {shown.map((r, i) => (
        <div key={i} className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="bg-muted rounded px-1.5 py-0.5">{r.source}</span>
          <span className="text-muted-foreground inline-flex items-center gap-0.5">
            <span className="bg-border h-px w-3" />
            <span className="text-[10px]">{r.relation}</span>
            <span className="text-muted-foreground">→</span>
          </span>
          <span className="bg-muted rounded px-1.5 py-0.5">{r.target}</span>
        </div>
      ))}
      {relations.length > initial && (
        <Button
          variant="link"
          size="sm"
          className="text-brand h-auto p-0 text-[10px]"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? t('step4.collapse') : t('step4.expandAll', { count: relations.length })}
        </Button>
      )}
    </div>
  )
}

/** 空状态文案。 */
export function ToolEmpty({ text }: { text: string }) {
  return <p className="text-muted-foreground py-2 text-center text-[11px]">{text}</p>
}
