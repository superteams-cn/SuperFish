import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2, Sparkles, ArrowRight, Code, Radio, AlertTriangle, RotateCcw } from 'lucide-react'

import { SystemLogTerminal } from '@/components/SystemLogTerminal'
import { Button } from '@/components/ui/button'
import { CollapsibleHeader } from '@/components/ui/collapsible-header'
import { NarrativeBeatFlow } from '@/components/step3/NarrativeBeatFlow'
import { useNarrativeRun } from '@/components/step3/useNarrativeRun'
import { StageIcon } from '@/components/common/StageIcon'
import { SoftProgress } from '@/components/common/SoftProgress'
import { generateReport } from '@/lib/api/report'
import type { SystemLog } from '@/lib/process-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

interface Props {
  simulationId: string
  systemLogs: SystemLog[]
  addLog: (msg: string) => void
  onUpdateStatus: (s: WorkflowStatus) => void
}

/** 步骤三（剧本推演）：角色在场景里演一遍，渲染 beat 流（说话/潜台词/内心独白/导演切场）。 */
export function Step3Narrative({ simulationId, systemLogs, addLog, onUpdateStatus }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const { phase, status, beats, startError, retry } = useNarrativeRun({
    simulationId,
    addLog,
    onUpdateStatus,
  })

  const [isGeneratingReport, setIsGeneratingReport] = useState(false)
  const [backstageOpen, setBackstageOpen] = useState(false)

  const handleGenerateReport = async () => {
    if (!simulationId || isGeneratingReport) return
    setIsGeneratingReport(true)
    addLog(t('log.startingReportGen'))
    try {
      const res = await generateReport({ simulation_id: simulationId, force_regenerate: false })
      if (res.success && res.data) {
        navigate(`/report/${res.data.report_id}`)
      } else {
        addLog(t('log.reportGenFailed', { error: res.error || t('common.unknownError') }))
        setIsGeneratingReport(false)
      }
    } catch (err) {
      addLog(t('log.reportGenException', { error: (err as Error).message }))
      setIsGeneratingReport(false)
    }
  }

  const done = phase === 2
  const beatCount = beats.length
  const progress = done
    ? 100
    : Math.min(Math.round(status.progress_percent ?? 0), 99) || (beatCount > 0 ? 12 : 6)
  const blocked = !!startError

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-5 py-8 sm:px-8">
        <div className="mx-auto max-w-2xl">
          {blocked ? (
            <div className="animate-rise-in mx-auto mt-6 max-w-md text-center">
              <div className="bg-destructive/10 text-destructive mx-auto flex h-14 w-14 items-center justify-center rounded-full">
                <AlertTriangle className="h-7 w-7" />
              </div>
              <h2 className="mt-4 text-xl font-semibold tracking-tight">
                {t('step3.cStartBlocked')}
              </h2>
              <p className="text-muted-foreground mt-2 text-sm leading-relaxed">{startError}</p>
              <Button
                variant="outline"
                className="mt-5 gap-2 rounded-full px-6"
                onClick={() => void retry()}
              >
                <RotateCcw className="h-4 w-4" />
                {t('step3.cRetry')}
              </Button>
            </div>
          ) : (
            <>
              <div className="animate-rise-in text-center">
                <StageIcon done={done} />
                <h2 className="text-2xl font-semibold tracking-tight">
                  {done ? t('narrative.actedTitle') : t('narrative.actingTitle')}
                </h2>
                <p className="text-muted-foreground mt-2">
                  {done ? t('narrative.actedSub', { count: beatCount }) : t('narrative.actingSub')}
                </p>
              </div>

              <div className="mt-6">
                <p className="text-muted-foreground mb-2 text-center text-sm">
                  {t('narrative.beatCount', { count: beatCount })}
                </p>
                <SoftProgress value={progress} floor={6} />
              </div>

              {done && (
                <div className="animate-rise-in mt-7 flex flex-col items-center gap-3">
                  <Button
                    variant="gradient"
                    className="h-12 gap-2 rounded-full px-8 text-base"
                    onClick={handleGenerateReport}
                    disabled={isGeneratingReport}
                  >
                    {isGeneratingReport ? (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    ) : (
                      <Sparkles className="h-5 w-5" />
                    )}
                    {isGeneratingReport ? t('step3.cGenerating') : t('step3.cNext')}
                    {!isGeneratingReport && <ArrowRight className="h-5 w-5" />}
                  </Button>
                </div>
              )}

              <div className="mt-8">
                {beats.length > 0 ? (
                  <NarrativeBeatFlow beats={beats} />
                ) : (
                  <div className="text-muted-foreground flex h-40 flex-col items-center justify-center gap-3 text-sm">
                    <Radio className="h-6 w-6 animate-pulse text-indigo-500" />
                    {t('narrative.waiting')}
                  </div>
                )}
              </div>
            </>
          )}

          <div className="mt-10">
            <CollapsibleHeader
              open={backstageOpen}
              onToggle={() => setBackstageOpen((o) => !o)}
              icon={<Code className="h-4 w-4" />}
              label={t('step3.cBackstage')}
              hint={t('step3.cBackstageHint')}
            />
            {backstageOpen && (
              <div className="mt-3">
                <SystemLogTerminal logs={systemLogs} badge={simulationId || 'NO_SIMULATION'} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
