import { useParams } from 'react-router-dom'

import { PagePlaceholder } from '@/components/PagePlaceholder'

export default function ReportPage() {
  const { reportId } = useParams()
  return <PagePlaceholder title="模拟报告" detail={`reportId: ${reportId}`} />
}
