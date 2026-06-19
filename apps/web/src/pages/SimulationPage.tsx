import { useParams } from 'react-router-dom'

import { PagePlaceholder } from '@/components/PagePlaceholder'

export default function SimulationPage() {
  const { simulationId } = useParams()
  return <PagePlaceholder title="模拟环境准备" detail={`simulationId: ${simulationId}`} />
}
