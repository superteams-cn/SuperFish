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

              {/* 活跃时段分解 */}
              <TimePeriods tc={tc} />
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

/** 活跃时段分解：高峰 / 工作 / 早间 / 低谷（hours 范围 + 活跃倍率）。 */
function TimePeriods({ tc }: { tc: NonNullable<SimulationConfig['time_config']> }) {
  const { t } = useTranslation()

  const periods = [
    { label: t('step2.peakHours'), hours: tc.peak_hours, mult: tc.peak_activity_multiplier },
    { label: t('step2.workHours'), hours: tc.work_hours, mult: tc.work_activity_multiplier },
    {
      label: t('step2.morningHours'),
      hours: tc.morning_hours,
      mult: tc.morning_activity_multiplier,
    },
    {
      label: t('step2.offPeakHours'),
      hours: tc.off_peak_hours,
      mult: tc.off_peak_activity_multiplier,
    },
  ].filter((p) => p.hours?.length)

  if (!periods.length) return null

  return (
    <div className="mt-3 flex flex-col gap-1.5">
      {periods.map((p) => (
        <div
          key={p.label}
          className="bg-card flex items-center gap-3 rounded-md border px-3 py-1.5 text-[11px]"
        >
          <span className="text-muted-foreground min-w-[64px] font-medium">{p.label}</span>
          <span className="text-foreground/80 flex-1 font-mono">{formatHours(p.hours)}</span>
          {p.mult != null && (
            <span
              className="bg-brand/10 text-brand rounded px-1.5 py-0.5 font-mono font-semibold"
              title={t('step2.activityMultiplier')}
            >
              ×{p.mult}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

/** 把小时数组格式化为可读时段字符串。 */
function formatHours(hours?: number[]) {
  if (!hours?.length) return '-'
  // 连续区间用 a:00-b:00；离散小时用逗号拼接（对齐旧版高峰时段展示）。
  const sorted = [...hours].sort((a, b) => a - b)
  const isContiguous = sorted.every((h, i) => i === 0 || h === sorted[i - 1] + 1)
  if (isContiguous && sorted.length > 1) {
    return `${sorted[0]}:00-${sorted[sorted.length - 1]}:00`
  }
  return sorted.map((h) => `${h}:00`).join(', ')
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
