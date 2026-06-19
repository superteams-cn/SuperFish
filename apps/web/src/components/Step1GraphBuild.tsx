import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'

import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { createSimulation } from '@/lib/api/simulation'
import type {
  BuildProgress,
  GraphData,
  OntologyItem,
  OntologyProgress,
  ProjectData,
  SystemLog,
} from '@/lib/process-types'
import { cn } from '@/lib/utils'

interface Step1Props {
  currentPhase: number // -1 上传 / 0 本体 / 1 构建 / 2 完成
  projectData: ProjectData | null
  ontologyProgress: OntologyProgress | null
  buildProgress: BuildProgress | null
  graphData: GraphData | null
  systemLogs: SystemLog[]
}

type SelectedItem = (OntologyItem & { itemType: 'entity' | 'relation' }) | null

/** 步骤一：图谱构建（本体生成 → GraphRAG 构建 → 完成进入环境搭建）。 */
export function Step1GraphBuild({
  currentPhase,
  projectData,
  ontologyProgress,
  buildProgress,
  graphData,
  systemLogs,
}: Step1Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [selected, setSelected] = useState<SelectedItem>(null)
  const [creating, setCreating] = useState(false)

  const stats = {
    nodes: graphData?.node_count ?? graphData?.nodes?.length ?? 0,
    edges: graphData?.edge_count ?? graphData?.edges?.length ?? 0,
    types: projectData?.ontology?.entity_types?.length ?? 0,
  }

  const entityName = (schemaName: string) =>
    projectData?.ontology?.entity_types?.find((e) => e.name === schemaName)?.name || schemaName

  // 进入环境搭建：创建 simulation 后跳转
  const handleEnterEnvSetup = async () => {
    if (!projectData?.project_id || !projectData?.graph_id) return
    setCreating(true)
    try {
      const res = await createSimulation({
        project_id: projectData.project_id,
        graph_id: projectData.graph_id,
        enable_twitter: true,
        enable_reddit: true,
      })
      if (res.success && res.data?.simulation_id) {
        navigate(`/simulation/${res.data.simulation_id}`)
      } else {
        alert(t('step1.createSimulationFailed', { error: res.error || t('common.unknownError') }))
      }
    } catch (err) {
      alert(t('step1.createSimulationException', { error: (err as Error).message }))
    } finally {
      setCreating(false)
    }
  }

  const badge = (cls: string, text: string) => (
    <span className={cn('rounded px-2 py-1 text-[10px] font-semibold uppercase', cls)}>{text}</span>
  )

  return (
    <div className="flex h-full flex-col overflow-hidden bg-muted/30">
      <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-6">
        {/* 步骤 01：本体生成 */}
        <div
          className={cn(
            'relative rounded-lg border bg-card p-5 shadow-sm transition',
            currentPhase === 0 && 'border-[#FF5722] shadow-md',
          )}
        >
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xl font-bold text-muted-foreground">01</span>
              <span className="text-sm font-semibold">{t('step1.ontologyGeneration')}</span>
            </div>
            {currentPhase > 0
              ? badge('bg-green-100 text-green-700', t('step1.ontologyCompleted'))
              : currentPhase === 0
                ? badge('bg-[#FF5722] text-white', t('step1.ontologyGenerating'))
                : badge('bg-muted text-muted-foreground', t('step1.ontologyPending'))}
          </div>
          <p className="mb-2 font-mono text-[10px] text-muted-foreground">
            POST /api/graph/ontology/generate
          </p>
          <p className="mb-4 text-xs leading-relaxed text-muted-foreground">
            {t('step1.ontologyDesc')}
          </p>

          {currentPhase === 0 && ontologyProgress && (
            <div className="mb-3 flex items-center gap-2 text-xs text-[#FF5722]">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>{ontologyProgress.message || t('step1.analyzingDocs')}</span>
            </div>
          )}

          {/* 本体详情浮层 */}
          {selected && (
            <div className="absolute inset-x-5 bottom-5 top-16 z-10 flex flex-col overflow-hidden rounded-md border bg-background/95 shadow-lg backdrop-blur">
              <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="rounded bg-foreground px-1.5 py-0.5 text-[9px] font-bold uppercase text-background">
                    {selected.itemType === 'entity' ? t('step1.badgeEntity') : t('step1.badgeRelation')}
                  </span>
                  <span className="text-sm font-bold">{selected.name}</span>
                </div>
                <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground">
                  ×
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                <p className="mb-4 border-b border-dashed pb-3 text-xs text-foreground/80">
                  {selected.description}
                </p>
                {!!selected.attributes?.length && (
                  <div className="mb-4">
                    <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">
                      {t('step1.attributes')}
                    </span>
                    <div className="flex flex-col gap-1.5">
                      {selected.attributes.map((attr) => (
                        <div key={attr.name} className="flex flex-wrap items-baseline gap-1.5 rounded bg-muted/50 p-1 text-[11px]">
                          <span className="font-mono font-semibold">{attr.name}</span>
                          <span className="text-[10px] text-muted-foreground">({attr.type})</span>
                          <span className="flex-1 text-muted-foreground">{attr.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {!!selected.examples?.length && (
                  <div className="mb-4">
                    <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">
                      {t('step1.examples')}
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.examples.map((ex) => (
                        <span key={ex} className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
                          {ex}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {!!selected.source_targets?.length && (
                  <div className="mb-4">
                    <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">
                      {t('step1.connections')}
                    </span>
                    <div className="flex flex-col gap-1.5">
                      {selected.source_targets.map((conn, idx) => (
                        <div key={idx} className="flex items-center gap-2 rounded bg-muted/50 p-1.5 font-mono text-[11px]">
                          <span className="font-semibold">{entityName(conn.source)}</span>
                          <span className="text-muted-foreground">→</span>
                          <span className="font-semibold">{entityName(conn.target)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 实体类型标签 */}
          {projectData?.ontology?.entity_types && (
            <div className={cn('mt-3 transition', selected && 'pointer-events-none opacity-30')}>
              <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">
                {t('step1.generatedEntityTypes')}
              </span>
              <div className="flex flex-wrap gap-2">
                {projectData.ontology.entity_types.map((entity) => (
                  <span
                    key={entity.name}
                    onClick={() => setSelected({ ...entity, itemType: 'entity' })}
                    className="cursor-pointer rounded border bg-muted px-2.5 py-1 font-mono text-[11px] hover:bg-accent"
                  >
                    {entity.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 关系类型标签 */}
          {projectData?.ontology?.edge_types && (
            <div className={cn('mt-3 transition', selected && 'pointer-events-none opacity-30')}>
              <span className="mb-2 block text-[10px] font-semibold text-muted-foreground">
                {t('step1.generatedRelationTypes')}
              </span>
              <div className="flex flex-wrap gap-2">
                {projectData.ontology.edge_types.map((rel) => (
                  <span
                    key={rel.name}
                    onClick={() => setSelected({ ...rel, itemType: 'relation' })}
                    className="cursor-pointer rounded border bg-muted px-2.5 py-1 font-mono text-[11px] hover:bg-accent"
                  >
                    {rel.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 步骤 02：图谱构建 */}
        <div
          className={cn(
            'rounded-lg border bg-card p-5 shadow-sm transition',
            currentPhase === 1 && 'border-[#FF5722] shadow-md',
          )}
        >
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xl font-bold text-muted-foreground">02</span>
              <span className="text-sm font-semibold">{t('step1.graphRagBuild')}</span>
            </div>
            {currentPhase > 1
              ? badge('bg-green-100 text-green-700', t('step1.ontologyCompleted'))
              : currentPhase === 1
                ? badge('bg-[#FF5722] text-white', `${buildProgress?.progress || 0}%`)
                : badge('bg-muted text-muted-foreground', t('step1.ontologyPending'))}
          </div>
          <p className="mb-2 font-mono text-[10px] text-muted-foreground">POST /api/graph/build</p>
          <p className="mb-4 text-xs leading-relaxed text-muted-foreground">{t('step1.graphRagDesc')}</p>
          <div className="grid grid-cols-3 gap-3 rounded-md bg-muted/50 p-4">
            {[
              { v: stats.nodes, l: t('step1.entityNodes') },
              { v: stats.edges, l: t('step1.relationEdges') },
              { v: stats.types, l: t('step1.schemaTypes') },
            ].map((s, i) => (
              <div key={i} className="text-center">
                <span className="block font-mono text-xl font-bold">{s.v}</span>
                <span className="mt-1 block text-[9px] uppercase text-muted-foreground">{s.l}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 步骤 03：完成 */}
        <div
          className={cn(
            'rounded-lg border bg-card p-5 shadow-sm transition',
            currentPhase >= 2 && 'border-[#FF5722] shadow-md',
          )}
        >
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xl font-bold text-muted-foreground">03</span>
              <span className="text-sm font-semibold">{t('step1.buildComplete')}</span>
            </div>
            {currentPhase >= 2 && badge('bg-[#FF5722] text-white', t('step1.inProgress'))}
          </div>
          <p className="mb-2 font-mono text-[10px] text-muted-foreground">POST /api/simulation/create</p>
          <p className="mb-4 text-xs leading-relaxed text-muted-foreground">{t('step1.buildCompleteDesc')}</p>
          <button
            onClick={handleEnterEnvSetup}
            disabled={currentPhase < 2 || creating}
            className="flex w-full items-center justify-center gap-2 rounded bg-foreground py-3.5 text-xs font-semibold text-background transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {creating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {creating ? t('step1.creating') : `${t('step1.enterEnvSetup')} ➝`}
          </button>
        </div>
      </div>

      {/* 系统日志终端 */}
      <SystemLogTerminal logs={systemLogs} badge={projectData?.project_id || 'NO_PROJECT'} />
    </div>
  )
}
