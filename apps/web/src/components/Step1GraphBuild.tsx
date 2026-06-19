import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { OntologyCard } from '@/components/step1/OntologyCard'
import { GraphBuildCard } from '@/components/step1/GraphBuildCard'
import { CompleteCard } from '@/components/step1/CompleteCard'
import type {
  BuildProgress,
  GraphData,
  OntologyProgress,
  ProjectData,
  SystemLog,
} from '@/lib/process-types'

interface Step1Props {
  currentPhase: number // -1 上传 / 0 本体 / 1 构建 / 2 完成
  projectData: ProjectData | null
  ontologyProgress: OntologyProgress | null
  buildProgress: BuildProgress | null
  graphData: GraphData | null
  systemLogs: SystemLog[]
}

/** 步骤一：图谱构建（本体生成 → GraphRAG 构建 → 完成进入环境搭建）。 */
export function Step1GraphBuild({
  currentPhase,
  projectData,
  ontologyProgress,
  buildProgress,
  graphData,
  systemLogs,
}: Step1Props) {
  return (
    <div className="bg-muted/30 flex h-full flex-col overflow-hidden">
      <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-6">
        <OntologyCard
          phase={currentPhase}
          projectData={projectData}
          ontologyProgress={ontologyProgress}
        />
        <GraphBuildCard
          phase={currentPhase}
          projectData={projectData}
          buildProgress={buildProgress}
          graphData={graphData}
        />
        <CompleteCard phase={currentPhase} projectData={projectData} />
      </div>

      <SystemLogTerminal logs={systemLogs} badge={projectData?.project_id || 'NO_PROJECT'} />
    </div>
  )
}
