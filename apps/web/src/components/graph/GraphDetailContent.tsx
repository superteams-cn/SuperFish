import { useTranslation } from 'react-i18next'
import { ChevronDown } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { GraphEdge, GraphNode } from '@/lib/graph-types'

type TFn = ReturnType<typeof useTranslation>['t']

function str(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return dateStr
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  if (!value) return null
  return (
    <div className="mb-2.5 flex flex-wrap gap-x-2">
      <span className="text-muted-foreground min-w-[72px] text-xs font-medium">{label}:</span>
      <span className={cn('flex-1 break-words', mono && 'font-mono text-xs')}>{value}</span>
    </div>
  )
}

/** 节点详情：名称 / 摘要（主内容）/ 关键属性（人话化）/ 创建时间。
 *  隐藏对小白无用的工程信息：UUID、Entity 等技术标签、与类型徽章重复的 ontology_type。 */
export function NodeDetail({ data, t }: { data: GraphNode; t: TFn }) {
  const attrs = (data.attributes ?? {}) as Record<string, unknown>
  // 属性名人话化；隐藏纯技术 / 与徽章重复的字段
  const propLabel: Record<string, string> = {
    platform: t('graph.propPlatform'),
    activity_count: t('graph.propActivityCount'),
  }
  const hidden = new Set(['summary', 'ontology_type'])
  const attrEntries = Object.entries(attrs).filter(([k]) => !hidden.has(k))

  return (
    <div className="space-y-4">
      <div>
        <div className="text-muted-foreground mb-0.5 text-xs">{t('graph.fieldName')}</div>
        <div className="text-base font-semibold leading-tight">{str(data.name)}</div>
      </div>

      {data.summary && (
        <div className="border-t pt-3">
          <div className="text-muted-foreground mb-1.5 text-xs font-semibold">
            {t('graph.fieldSummary')}
          </div>
          <p className="text-sm leading-relaxed">{str(data.summary)}</p>
        </div>
      )}

      {attrEntries.length > 0 && (
        <div className="border-t pt-3">
          <div className="text-muted-foreground mb-2 text-xs font-semibold">
            {t('graph.fieldProperties')}
          </div>
          <div className="flex flex-col gap-2">
            {attrEntries.map(([k, v]) => (
              <div key={k} className="flex gap-2 text-xs">
                <span className="text-muted-foreground min-w-[72px] font-medium">
                  {propLabel[k] ?? k}
                </span>
                <span className="flex-1 break-words">{str(v) || '—'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.created_at && (
        <div className="text-muted-foreground border-t pt-3 text-xs">
          {t('graph.fieldCreated')}：{formatDateTime(data.created_at)}
        </div>
      )}
    </div>
  )
}

/** 边详情：自环组（可逐条展开）或普通有向边。 */
export function EdgeDetail({
  data,
  expanded,
  onToggle,
  t,
}: {
  data: Record<string, unknown>
  expanded: Set<string>
  onToggle: (id: string) => void
  t: TFn
}) {
  // 自环组
  if (data.isSelfLoopGroup) {
    const loops = (data.selfLoopEdges as GraphEdge[]) ?? []
    return (
      <div>
        <div className="mb-3 flex items-center gap-2 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm font-medium">
          {str(data.source_name)} · {t('graph.selfRelations')}
          <span className="bg-background text-muted-foreground ml-auto rounded-full px-2 py-0.5 text-xs">
            {str(data.selfLoopCount)} {t('common.items')}
          </span>
        </div>
        <div className="flex flex-col gap-2">
          {loops.map((loop, idx) => {
            const id = loop.uuid || String(idx)
            const open = expanded.has(id)
            return (
              <div key={id} className="bg-muted/40 overflow-hidden rounded-md border">
                <button
                  onClick={() => onToggle(id)}
                  className="hover:bg-muted flex w-full items-center gap-2 px-3 py-2 text-left"
                >
                  <span className="text-muted-foreground bg-background rounded px-1.5 py-0.5 text-[10px] font-semibold">
                    #{idx + 1}
                  </span>
                  <span className="flex-1 truncate text-xs font-medium">
                    {loop.name || loop.fact_type || 'RELATED'}
                  </span>
                  <ChevronDown
                    className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')}
                  />
                </button>
                {open && (
                  <div className="border-t px-3 py-2">
                    <Row label="UUID" value={str(loop.uuid)} mono />
                    <Row label={t('graph.fieldFact')} value={str(loop.fact)} />
                    <Row label={t('graph.fieldType')} value={str(loop.fact_type)} />
                    <Row label={t('graph.fieldCreated')} value={formatDateTime(loop.created_at)} />
                    {(loop.episodes as string[] | undefined)?.length ? (
                      <div className="mt-2">
                        <div className="text-muted-foreground mb-1 text-xs font-semibold">
                          {t('graph.fieldEpisodes')}
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {(loop.episodes as string[]).map((ep) => (
                            <span
                              key={ep}
                              className="bg-background rounded border px-1.5 py-0.5 font-mono text-[10px]"
                            >
                              {ep}
                            </span>
                          ))}
                        </div>
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

  // 普通边
  const episodes = (data.episodes as string[]) ?? []
  return (
    <div>
      <div className="bg-muted/50 mb-3 rounded-md px-3 py-2 text-sm font-medium leading-relaxed">
        {str(data.source_name)} → {str(data.name) || 'RELATED_TO'} → {str(data.target_name)}
      </div>
      <Row label="UUID" value={str(data.uuid)} mono />
      <Row label={t('graph.fieldLabel')} value={str(data.name) || 'RELATED_TO'} />
      <Row label={t('graph.fieldType')} value={str(data.fact_type) || 'Unknown'} />
      <Row label={t('graph.fieldFact')} value={str(data.fact)} />
      <Row label={t('graph.fieldCreated')} value={formatDateTime(str(data.created_at))} />
      <Row label={t('graph.fieldValidFrom')} value={formatDateTime(str(data.valid_at))} />

      {episodes.length > 0 && (
        <div className="mt-4 border-t pt-3">
          <div className="text-muted-foreground mb-2 text-xs font-semibold">
            {t('graph.fieldEpisodes')}
          </div>
          <div className="flex flex-col gap-1.5">
            {episodes.map((ep) => (
              <span key={ep} className="bg-muted rounded border px-2 py-1 font-mono text-[10px]">
                {ep}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
