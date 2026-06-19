import { useTranslation } from 'react-i18next'
import { RefreshCw } from 'lucide-react'

import { StepCard } from '@/components/StepCard'
import { Button } from '@/components/ui/button'
import type { BuildProgress, GraphData, ProjectData } from '@/lib/process-types'

interface Props {
  phase: number
  projectData: ProjectData | null
  buildProgress: BuildProgress | null
  graphData: GraphData | null
  /** 重新构建图谱（force 重建，可恢复卡住或不满意的结果） */
  onRebuild?: () => void
}

/** 步骤 02：GraphRAG 构建（节点/边/Schema 统计）。 */
export function GraphBuildCard({ phase, projectData, buildProgress, graphData, onRebuild }: Props) {
  const { t } = useTranslation()

  const stats = {
    nodes: graphData?.node_count ?? graphData?.nodes?.length ?? 0,
    edges: graphData?.edge_count ?? graphData?.edges?.length ?? 0,
    types: projectData?.ontology?.entity_types?.length ?? 0,
  }

  const status = phase > 1 ? 'completed' : phase === 1 ? 'processing' : 'pending'
  const statusText =
    phase > 1
      ? t('step1.ontologyCompleted')
      : phase === 1
        ? `${buildProgress?.progress || 0}%`
        : t('step1.ontologyPending')

  return (
    <StepCard
      num="02"
      title={t('step1.graphRagBuild')}
      status={status}
      statusText={statusText}
      active={phase === 1}
      apiNote="POST /api/graph/build"
      description={t('step1.graphRagDesc')}
    >
      <div className="bg-muted/50 grid grid-cols-3 gap-3 rounded-md p-4">
        {[
          { v: stats.nodes, l: t('step1.entityNodes') },
          { v: stats.edges, l: t('step1.relationEdges') },
          { v: stats.types, l: t('step1.schemaTypes') },
        ].map((s, i) => (
          <div key={i} className="text-center">
            <span className="block font-mono text-xl font-bold">{s.v}</span>
            <span className="text-muted-foreground mt-1 block text-[9px] uppercase">{s.l}</span>
          </div>
        ))}
      </div>

      {/* 重新构建：phase≥1（构建中/已完成）均可点——构建卡住时也能据此恢复 */}
      {phase >= 1 && onRebuild && (
        <Button
          variant="outline"
          size="sm"
          onClick={onRebuild}
          className="mt-3 w-full gap-1.5"
          title={t('step1.rebuildGraphHint')}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${phase === 1 ? 'animate-spin' : ''}`} />
          {t('step1.rebuildGraph')}
        </Button>
      )}
    </StepCard>
  )
}
