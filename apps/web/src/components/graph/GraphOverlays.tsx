import { useTranslation } from 'react-i18next'

/** 图例（左下，含实体类型色块与节点/边计数）。图谱面板复用。 */
export function GraphLegend({
  typeColors,
  nodeCount,
  edgeCount,
}: {
  typeColors: Map<string, string>
  nodeCount: number
  edgeCount: number
}) {
  const { t } = useTranslation()
  if (typeColors.size === 0) return null
  return (
    <div className="bg-background/90 absolute bottom-3 left-3 z-10 max-w-[320px] rounded-md border p-2.5 text-xs shadow-sm backdrop-blur">
      <div className="text-muted-foreground mb-1.5 font-semibold uppercase tracking-wide">
        {t('graph.entityTypes')}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {Array.from(typeColors.entries()).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="truncate">{type}</span>
          </div>
        ))}
      </div>
      <div className="text-muted-foreground mt-1.5 border-t pt-1.5">
        {t('graph.nodesEdges', { nodes: nodeCount, edges: edgeCount })}
      </div>
    </div>
  )
}

/** 底部居中的「实时更新中」胶囊提示。图谱面板复用。 */
export function GraphRealtimeHint({ hint }: { hint: string }) {
  return (
    <div className="bg-foreground/75 text-background absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full px-4 py-2 text-xs font-medium shadow-lg backdrop-blur">
      <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
      {hint}
    </div>
  )
}
