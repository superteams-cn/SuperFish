import { useTranslation } from 'react-i18next'

import { StepCard } from '@/components/StepCard'
import { AgentConfigItem } from './AgentConfigItem'
import type { PlatformConfig, SimulationConfig } from '@/lib/step2-types'

interface Props {
  phase: number
  config: SimulationConfig | null
}

/** 步骤 03：生成双平台模拟配置（时间 / Agent / 平台算法 / LLM 推理）。 */
export function PlatformConfigCard({ phase, config }: Props) {
  const { t } = useTranslation()
  const tc = config?.time_config

  const status = phase > 2 ? 'completed' : phase === 2 ? 'processing' : 'pending'
  const statusText =
    phase > 2 ? t('common.completed') : phase === 2 ? t('step2.generating') : t('common.pending')

  const totalRounds =
    tc?.total_simulation_hours && tc?.minutes_per_round
      ? Math.floor((tc.total_simulation_hours * 60) / tc.minutes_per_round)
      : '-'

  return (
    <StepCard
      num="03"
      title={t('step2.dualPlatformConfig')}
      status={status}
      statusText={statusText}
      active={phase === 2}
      apiNote="POST /api/simulation/prepare"
      description={t('step2.dualPlatformConfigDesc')}
    >
      {config && (
        <div className="space-y-4">
          {/* 时间配置 */}
          {tc && (
            <div className="bg-muted/50 rounded-md p-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat
                  label={t('step2.simulationDuration')}
                  value={`${tc.total_simulation_hours ?? '-'} ${t('common.hours')}`}
                />
                <Stat
                  label={t('step2.roundDuration')}
                  value={`${tc.minutes_per_round ?? '-'} ${t('common.minutes')}`}
                />
                <Stat
                  label={t('step2.totalRounds')}
                  value={`${totalRounds} ${t('common.rounds')}`}
                />
                <Stat
                  label={t('step2.activePerHour')}
                  value={`${tc.agents_per_hour_min}-${tc.agents_per_hour_max}`}
                />
              </div>
            </div>
          )}

          {/* Agent 配置 */}
          {!!config.agent_configs?.length && (
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold">{t('step2.agentConfig')}</span>
                <span className="bg-muted rounded px-1.5 py-0.5 text-[10px]">
                  {config.agent_configs.length} {t('common.items')}
                </span>
              </div>
              <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
                {config.agent_configs.map((agent) => (
                  <AgentConfigItem key={agent.agent_id} agent={agent} />
                ))}
              </div>
            </div>
          )}

          {/* 平台推荐算法配置 */}
          <div>
            <span className="mb-2 block text-xs font-semibold">
              {t('step2.recommendAlgoConfig')}
            </span>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {config.twitter_config && (
                <PlatformBlock name={t('step2.platform1Name')} cfg={config.twitter_config} />
              )}
              {config.reddit_config && (
                <PlatformBlock name={t('step2.platform2Name')} cfg={config.reddit_config} />
              )}
            </div>
          </div>

          {/* LLM 配置推理 */}
          {config.generation_reasoning && (
            <div>
              <span className="mb-2 block text-xs font-semibold">
                {t('step2.llmConfigReasoning')}
              </span>
              <div className="space-y-2">
                {config.generation_reasoning
                  .split('|')
                  .slice(0, 2)
                  .map((reason, idx) => (
                    <p key={idx} className="bg-muted/50 text-foreground/80 rounded p-2 text-[11px]">
                      {reason.trim()}
                    </p>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </StepCard>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted-foreground block text-[10px]">{label}</span>
      <span className="text-sm font-semibold">{value}</span>
    </div>
  )
}

function PlatformBlock({ name, cfg }: { name: string; cfg: PlatformConfig }) {
  const { t } = useTranslation()
  const rows = [
    { l: t('step2.recencyWeight'), v: cfg.recency_weight },
    { l: t('step2.popularityWeight'), v: cfg.popularity_weight },
    { l: t('step2.relevanceWeight'), v: cfg.relevance_weight },
    { l: t('step2.viralThreshold'), v: cfg.viral_threshold },
    { l: t('step2.echoChamberStrength'), v: cfg.echo_chamber_strength },
  ]
  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 text-xs font-semibold">{name}</div>
      <div className="space-y-1">
        {rows.map((r) => (
          <div key={r.l} className="flex justify-between text-[11px]">
            <span className="text-muted-foreground">{r.l}</span>
            <span className="font-mono">{String(r.v ?? '-')}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
