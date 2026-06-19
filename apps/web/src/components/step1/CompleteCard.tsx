import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'

import { StepCard } from '@/components/StepCard'
import { Button } from '@/components/ui/button'
import { createSimulation } from '@/lib/api/simulation'
import type { ProjectData } from '@/lib/process-types'

interface Props {
  phase: number
  projectData: ProjectData | null
}

/** 步骤 03：构建完成（创建模拟并进入环境搭建）。 */
export function CompleteCard({ phase, projectData }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  const handleEnter = async () => {
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

  return (
    <StepCard
      num="03"
      title={t('step1.buildComplete')}
      status={phase >= 2 ? 'processing' : 'pending'}
      statusText={phase >= 2 ? t('step1.inProgress') : undefined}
      active={phase >= 2}
      apiNote="POST /api/simulation/create"
      description={t('step1.buildCompleteDesc')}
    >
      <Button className="w-full" onClick={handleEnter} disabled={phase < 2 || creating}>
        {creating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {creating ? t('step1.creating') : `${t('step1.enterEnvSetup')} ➝`}
      </Button>
    </StepCard>
  )
}
