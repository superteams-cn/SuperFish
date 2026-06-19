import { useParams } from 'react-router-dom'

import { PagePlaceholder } from '@/components/PagePlaceholder'

export default function ProcessPage() {
  const { projectId } = useParams()
  return <PagePlaceholder title="图谱构建流程" detail={`projectId: ${projectId}`} />
}
