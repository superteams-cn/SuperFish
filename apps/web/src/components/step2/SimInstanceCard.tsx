import { useTranslation } from 'react-i18next'

import { StepCard } from '@/components/StepCard'
import type { ProjectData } from '@/lib/process-types'

interface Props {
  phase: number
  projectData: ProjectData | null
  simulationId?: string
  taskId: string | null
}

/** 步骤 01：模拟实例初始化（展示 project/graph/simulation/task 标识）。 */
export function SimInstanceCard({ phase, projectData, simulationId, taskId }: Props) {
  const { t } = useTranslation()

  const rows = [
    { label: t('step2.projectIdLabel'), value: projectData?.project_id },
    { label: t('step2.graphIdLabel'), value: projectData?.graph_id },
    { label: t('step2.simulationIdLabel'), value: simulationId },
    { label: t('step2.taskIdLabel'), value: taskId || t('step2.asyncTaskDone') },
  ]

  return (
    <StepCard
      num="01"
      title={t('step2.simInstanceInit')}
      status={phase > 0 ? 'completed' : 'processing'}
      statusText={phase > 0 ? t('common.completed') : t('step2.initializing')}
      active={phase === 0}
      apiNote="POST /api/simulation/create"
      description={t('step2.simInstanceDesc')}
    >
      {simulationId && (
        <div className="bg-muted/50 space-y-2 rounded-md p-3">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{r.label}</span>
              <span className="font-mono">{String(r.value ?? '-')}</span>
            </div>
          ))}
        </div>
      )}
    </StepCard>
  )
}
