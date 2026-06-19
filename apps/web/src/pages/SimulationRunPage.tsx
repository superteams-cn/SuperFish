import { useParams } from 'react-router-dom'

import { PagePlaceholder } from '@/components/PagePlaceholder'

export default function SimulationRunPage() {
  const { simulationId } = useParams()
  return <PagePlaceholder title="模拟运行" detail={`simulationId: ${simulationId}`} />
}
