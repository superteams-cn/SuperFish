import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { AgentConfig } from '@/lib/step2-types'

/** 单个 Agent 行为配置卡片（活跃时间轴 + 行为参数）。 */
export function AgentConfigItem({ agent }: { agent: AgentConfig }) {
  const { t } = useTranslation()
  const sentiment = agent.sentiment_bias ?? 0

  return (
    <div className="bg-card rounded-md border p-3">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-bold">Agent {agent.agent_id}</span>
          <span className="text-muted-foreground text-xs">{agent.entity_name}</span>
        </div>
        <div className="flex gap-1">
          <span className="bg-muted rounded px-1.5 py-0.5 text-[10px]">{agent.entity_type}</span>
          {agent.stance && (
            <span className="bg-muted rounded px-1.5 py-0.5 text-[10px]">{agent.stance}</span>
          )}
        </div>
      </div>

      {/* 24 小时活跃时间轴 */}
      <div className="mb-3">
        <span className="text-muted-foreground text-[10px]">{t('step2.activeTimePeriod')}</span>
        <div className="mt-1 flex gap-px">
          {Array.from({ length: 24 }, (_, h) => (
            <div
              key={h}
              title={`${h}:00`}
              className={cn(
                'h-3 flex-1 rounded-[1px]',
                agent.active_hours?.includes(h) ? 'bg-[#FF5722]' : 'bg-muted',
              )}
            />
          ))}
        </div>
        <div className="text-muted-foreground mt-0.5 flex justify-between text-[8px]">
          <span>0</span>
          <span>6</span>
          <span>12</span>
          <span>18</span>
          <span>24</span>
        </div>
      </div>

      {/* 行为参数 */}
      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <Param label={t('step2.postsPerHour')} value={agent.posts_per_hour} />
        <Param label={t('step2.commentsPerHour')} value={agent.comments_per_hour} />
        <Param
          label={t('step2.responseDelay')}
          value={`${agent.response_delay_min}-${agent.response_delay_max}min`}
        />
        <div>
          <span className="text-muted-foreground block text-[9px]">{t('step2.activityLevel')}</span>
          <div className="bg-muted mt-1 h-1.5 w-full rounded-full">
            <div
              className="h-full rounded-full bg-[#FF5722]"
              style={{ width: `${(agent.activity_level ?? 0) * 100}%` }}
            />
          </div>
        </div>
        <div>
          <span className="text-muted-foreground block text-[9px]">{t('step2.sentimentBias')}</span>
          <span
            className={cn(
              'font-mono font-semibold',
              sentiment > 0
                ? 'text-green-600'
                : sentiment < 0
                  ? 'text-red-600'
                  : 'text-muted-foreground',
            )}
          >
            {sentiment > 0 ? '+' : ''}
            {sentiment.toFixed(1)}
          </span>
        </div>
        <Param label={t('step2.influenceWeight')} value={agent.influence_weight?.toFixed(1)} />
      </div>
    </div>
  )
}

function Param({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <span className="text-muted-foreground block text-[9px]">{label}</span>
      <span className="font-mono font-semibold">{String(value ?? '-')}</span>
    </div>
  )
}
