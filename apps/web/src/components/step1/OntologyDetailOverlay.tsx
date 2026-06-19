import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { OntologyItem } from '@/lib/process-types'

export type SelectedOntologyItem = (OntologyItem & { itemType: 'entity' | 'relation' }) | null

interface Props {
  item: NonNullable<SelectedOntologyItem>
  /** 把 schema 名解析为实体显示名 */
  resolveEntityName: (schemaName: string) => string
  onClose: () => void
}

/** 本体条目详情浮层（属性 / 示例 / 连接关系）。 */
export function OntologyDetailOverlay({ item, resolveEntityName, onClose }: Props) {
  const { t } = useTranslation()

  return (
    <div className="bg-background/95 absolute inset-x-5 bottom-5 top-16 z-10 flex flex-col overflow-hidden rounded-md border shadow-lg backdrop-blur">
      <div className="bg-muted/50 flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Badge className="text-[9px] uppercase">
            {item.itemType === 'entity' ? t('step1.badgeEntity') : t('step1.badgeRelation')}
          </Badge>
          <span className="text-sm font-bold">{item.name}</span>
        </div>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <p className="text-foreground/80 mb-4 border-b border-dashed pb-3 text-xs">
          {item.description}
        </p>

        {!!item.attributes?.length && (
          <div className="mb-4">
            <span className="text-muted-foreground mb-2 block text-[10px] font-semibold">
              {t('step1.attributes')}
            </span>
            <div className="flex flex-col gap-1.5">
              {item.attributes.map((attr) => (
                <div
                  key={attr.name}
                  className="bg-muted/50 flex flex-wrap items-baseline gap-1.5 rounded p-1 text-[11px]"
                >
                  <span className="font-mono font-semibold">{attr.name}</span>
                  <span className="text-muted-foreground text-[10px]">({attr.type})</span>
                  <span className="text-muted-foreground flex-1">{attr.description}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {!!item.examples?.length && (
          <div className="mb-4">
            <span className="text-muted-foreground mb-2 block text-[10px] font-semibold">
              {t('step1.examples')}
            </span>
            <div className="flex flex-wrap gap-1.5">
              {item.examples.map((ex) => (
                <span
                  key={ex}
                  className="text-muted-foreground rounded-full border px-2 py-0.5 text-[11px]"
                >
                  {ex}
                </span>
              ))}
            </div>
          </div>
        )}

        {!!item.source_targets?.length && (
          <div className="mb-4">
            <span className="text-muted-foreground mb-2 block text-[10px] font-semibold">
              {t('step1.connections')}
            </span>
            <div className="flex flex-col gap-1.5">
              {item.source_targets.map((conn, idx) => (
                <div
                  key={idx}
                  className="bg-muted/50 flex items-center gap-2 rounded p-1.5 font-mono text-[11px]"
                >
                  <span className="font-semibold">{resolveEntityName(conn.source)}</span>
                  <span className="text-muted-foreground">→</span>
                  <span className="font-semibold">{resolveEntityName(conn.target)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
