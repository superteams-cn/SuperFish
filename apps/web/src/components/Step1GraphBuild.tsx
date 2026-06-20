import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Loader2,
  CheckCircle2,
  ChevronDown,
  RefreshCw,
  Code,
  Sparkles,
  ArrowRight,
} from 'lucide-react'
import { toast } from 'sonner'

import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { createSimulation, listSimulations } from '@/lib/api/simulation'
import { cn } from '@/lib/utils'
import type {
  BuildProgress,
  GraphData,
  OntologyItem,
  OntologyProgress,
  ProjectData,
  SystemLog,
} from '@/lib/process-types'

const GRADIENT_BTN =
  'bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/40'

interface Step1Props {
  currentPhase: number // -1 上传 / 0 本体 / 1 构建 / 2 完成
  projectData: ProjectData | null
  ontologyProgress: OntologyProgress | null
  buildProgress: BuildProgress | null
  graphData: GraphData | null
  systemLogs: SystemLog[]
  /** 重新构建图谱（force） */
  onRebuild?: () => void
}

/**
 * 旅程第一站「读懂你的世界」：AI 读材料 → 理清人物关系 → 准备好。
 * 主舞台：进展 + 角色/关系（hover 看说明）+ 下一步；重来/重建/原始日志/ID 沉入「幕后」。
 */
export function Step1GraphBuild({
  currentPhase,
  projectData,
  ontologyProgress,
  buildProgress,
  graphData,
  systemLogs,
  onRebuild,
}: Step1Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [backstageOpen, setBackstageOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const busy = creating || rebuilding

  const nodes = graphData?.node_count ?? graphData?.nodes?.length ?? 0
  const edges = graphData?.edge_count ?? graphData?.edges?.length ?? 0
  const roles = projectData?.ontology?.entity_types ?? []
  const rels = projectData?.ontology?.edge_types ?? []
  const building = currentPhase === 1
  const done = currentPhase >= 2
  const progress = buildProgress?.progress ?? 0

  const title = done
    ? t('step1.cUnderstood')
    : building
      ? t('step1.cUnderstanding')
      : t('step1.cReading')
  const sub =
    currentPhase <= 0
      ? ontologyProgress?.message || t('step1.cReadingSub')
      : t('step1.cFound', { nodes, edges })

  /**
   * 进入下一站 / 重建环境。
   * forceNew=false：优先复用项目下已有模拟（续做），无则新建。
   * forceNew=true：丢弃已有，基于当前图谱新建全新环境。
   */
  const handleEnter = async (forceNew: boolean) => {
    if (!projectData?.project_id || !projectData?.graph_id || busy) return
    const setBusy = forceNew ? setRebuilding : setCreating
    setBusy(true)
    try {
      if (!forceNew) {
        const existing = await listSimulations(projectData.project_id)
        if (existing.success && existing.data && existing.data.length > 0) {
          const sims = existing.data // 后端按 created_at 倒序
          const target = sims.find((s) => s.config_generated || s.status === 'ready') || sims[0]
          if (target.simulation_id) {
            navigate(`/simulation/${target.simulation_id}`)
            return
          }
        }
      }
      const res = await createSimulation({
        project_id: projectData.project_id,
        graph_id: projectData.graph_id,
        enable_twitter: true,
        enable_reddit: true,
      })
      if (res.success && res.data?.simulation_id) {
        navigate(`/simulation/${res.data.simulation_id}`)
      } else {
        toast.error(
          t('step1.createSimulationFailed', { error: res.error || t('common.unknownError') }),
        )
      }
    } catch (err) {
      toast.error(t('step1.createSimulationException', { error: (err as Error).message }))
    } finally {
      setBusy(false)
    }
  }

  const handleRebuildEnv = () => {
    if (busy) return
    if (!window.confirm(t('step1.rebuildEnvConfirm'))) return
    void handleEnter(true)
  }

  const resolveEntityName = (schemaName: string) =>
    roles.find((e) => e.name === schemaName)?.name || schemaName

  // 角色/关系标签：hover 在上方浮出全面说明（描述 + 示例 + 属性 + 关系连接）
  const tagGroup = (items: OntologyItem[], label: string) =>
    items.length > 0 && (
      <div>
        <p className="text-muted-foreground mb-3 text-sm">{label}</p>
        <div className="flex flex-wrap gap-2">
          {items.map((it) => (
            <Tooltip key={it.name}>
              <TooltipTrigger asChild>
                <span className="bg-secondary cursor-default rounded-full px-3 py-1 text-sm backdrop-blur-xl">
                  {it.name}
                </span>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-sm space-y-1.5 p-3 leading-relaxed">
                <p className="font-medium">{it.name}</p>
                {it.description && <p className="opacity-90">{it.description}</p>}
                {!!it.examples?.length && (
                  <p>
                    <span className="opacity-60">{t('step1.examples')}：</span>
                    {it.examples.join('、')}
                  </p>
                )}
                {!!it.attributes?.length && (
                  <p>
                    <span className="opacity-60">{t('step1.attributes')}：</span>
                    {it.attributes.map((a) => a.name).join('、')}
                  </p>
                )}
                {!!it.source_targets?.length && (
                  <p>
                    <span className="opacity-60">{t('step1.connections')}：</span>
                    {it.source_targets
                      .map((c) => `${resolveEntityName(c.source)} → ${resolveEntityName(c.target)}`)
                      .join('，')}
                  </p>
                )}
              </TooltipContent>
            </Tooltip>
          ))}
        </div>
      </div>
    )

  return (
    <TooltipProvider delayDuration={150}>
      <div className="relative flex h-full flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto px-5 py-10 sm:px-8">
          <div className="mx-auto max-w-lg">
            {/* 舞台主体 */}
            <div className="animate-rise-in text-center">
              <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white shadow-lg">
                {done ? (
                  <CheckCircle2 className="h-8 w-8" />
                ) : (
                  <Loader2 className="h-8 w-8 animate-spin" />
                )}
              </div>
              <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
              <p className="text-muted-foreground mt-2">{sub}</p>
            </div>

            {/* 构建中的软进度 */}
            {building && (
              <div className="bg-muted mt-6 h-1.5 overflow-hidden rounded-full">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 transition-all duration-500"
                  style={{ width: `${Math.max(progress, 5)}%` }}
                />
              </div>
            )}

            {/* 发现的角色 / 关系（hover 看说明） */}
            {(roles.length > 0 || rels.length > 0) && (
              <div className="glass animate-rise-in mt-6 space-y-4 rounded-2xl p-5">
                {tagGroup(roles, t('step1.cRoles'))}
                {tagGroup(rels, t('step1.cRelations'))}
              </div>
            )}

            {/* 完成 → 唯一主操作：下一步 */}
            {done && (
              <div className="animate-rise-in mt-8 flex justify-center">
                <Button
                  className={`${GRADIENT_BTN} h-12 gap-2 rounded-full px-8 text-base`}
                  onClick={() => handleEnter(false)}
                  disabled={busy}
                >
                  {creating ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <Sparkles className="h-5 w-5" />
                  )}
                  {creating ? t('step1.cEntering') : t('step1.cNext')}
                  {!creating && <ArrowRight className="h-5 w-5" />}
                </Button>
              </div>
            )}

            {/* 幕后：重来 / 重建 / 原始日志 / ID */}
            <div className="mt-10">
              <button
                type="button"
                onClick={() => setBackstageOpen((o) => !o)}
                className="text-muted-foreground hover:text-foreground flex w-full items-center justify-between rounded-xl border border-dashed px-4 py-3 text-sm transition-colors"
              >
                <span className="flex items-center gap-2">
                  <Code className="h-4 w-4" />
                  {t('step1.cBackstage')}
                  <span className="text-muted-foreground/70 hidden text-xs sm:inline">
                    · {t('step1.cBackstageHint')}
                  </span>
                </span>
                <ChevronDown
                  className={cn('h-4 w-4 transition-transform', backstageOpen && 'rotate-180')}
                />
              </button>

              {backstageOpen && (
                <div className="mt-3 space-y-3">
                  <div className="flex flex-wrap gap-2">
                    {onRebuild && currentPhase >= 1 && (
                      <Button variant="outline" size="sm" onClick={onRebuild} className="gap-1.5">
                        <RefreshCw className={cn('h-3.5 w-3.5', building && 'animate-spin')} />
                        {t('step1.cRebuildWorld')}
                      </Button>
                    )}
                    {done && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleRebuildEnv}
                        disabled={busy}
                        className="gap-1.5"
                      >
                        <RefreshCw className={cn('h-3.5 w-3.5', rebuilding && 'animate-spin')} />
                        {t('step1.rebuildEnv')}
                      </Button>
                    )}
                  </div>
                  <SystemLogTerminal
                    logs={systemLogs}
                    badge={projectData?.project_id || 'NO_PROJECT'}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  )
}
