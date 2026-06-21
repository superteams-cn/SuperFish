import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { startSimulation, getRunStatus, getRunStatusDetail } from '@/lib/api/simulation'
import { usePolling } from '@/hooks/usePolling'
import type { BeatItem, NarrativeRunStatus } from '@/lib/narrative-types'
import type { WorkflowStatus } from '@/components/WorkflowLayout'

interface Options {
  simulationId: string
  addLog: (msg: string) => void
  onUpdateStatus: (s: WorkflowStatus) => void
}

/**
 * 剧本推演运行编排：单路轮询 run-status/detail 拿 beat 流；进入时 resume-or-start。
 *
 * 与 useSimulationRun（社媒双平台）平行而独立——叙事是单条 beat 流，无双平台/轮次概念，
 * 故不复用那套 twitter/reddit 状态机，避免互相污染。
 */
export function useNarrativeRun({ simulationId, addLog, onUpdateStatus }: Options) {
  const { t } = useTranslation()

  const [phase, setPhase] = useState(0) // 0 未开始 / 1 推演中 / 2 已完成
  const [status, setStatus] = useState<NarrativeRunStatus>({})
  const [beats, setBeats] = useState<BeatItem[]>([])
  const [startError, setStartError] = useState<string | null>(null)

  const seenSeq = useRef<Set<number>>(new Set())
  const initedRef = useRef(false)
  const pollRef = useRef<() => void | Promise<void>>(() => {})

  const poll = usePolling(() => pollRef.current(), 2500)

  const ingest = useCallback((data: NarrativeRunStatus) => {
    setStatus(data)
    const incoming = data.all_beats || []
    const fresh: BeatItem[] = []
    incoming.forEach((b) => {
      if (!seenSeq.current.has(b.seq)) {
        seenSeq.current.add(b.seq)
        fresh.push({ ...b, _uniqueId: `beat-${b.seq}` })
      }
    })
    if (fresh.length) setBeats((prev) => [...prev, ...fresh])
  }, [])

  const fetchDetail = useCallback(async () => {
    if (!simulationId) return
    try {
      const res = await getRunStatusDetail(simulationId)
      if (!res.success || !res.data) return
      const data = res.data as unknown as NarrativeRunStatus
      ingest(data)
      const rs = data.runner_status
      if (rs === 'completed' || rs === 'failed' || rs === 'interrupted') {
        addLog(rs === 'completed' ? t('log.simCompleted') : t('narrative.runEnded', { status: rs }))
        setPhase(2)
        poll.stop()
        onUpdateStatus(rs === 'failed' ? 'error' : 'completed')
      }
    } catch (err) {
      console.warn('获取叙事 beat 失败:', err)
    }
  }, [simulationId, ingest, addLog, onUpdateStatus, poll, t])

  pollRef.current = fetchDetail

  const doStart = useCallback(async () => {
    if (!simulationId) return
    setPhase(0)
    setStartError(null)
    setBeats([])
    seenSeq.current = new Set()
    poll.stop()

    addLog(t('narrative.starting'))
    onUpdateStatus('processing')
    try {
      const res = await startSimulation({
        simulation_id: simulationId,
        platform: 'parallel',
        force: true,
      })
      if (res.success) {
        addLog(t('narrative.engineStarted'))
        setPhase(1)
        poll.start()
      } else {
        const msg = res.error || t('common.unknownError')
        addLog(t('log.startFailed', { error: msg }))
        setStartError(msg)
        onUpdateStatus('error')
      }
    } catch (err) {
      const msg = (err as Error).message
      setStartError(msg)
      onUpdateStatus('error')
    }
  }, [simulationId, poll, addLog, onUpdateStatus, t])

  const resumeOrStart = useCallback(async () => {
    if (!simulationId) return
    let data: NarrativeRunStatus | null = null
    try {
      const res = await getRunStatus(simulationId)
      if (res.success && res.data) data = res.data as unknown as NarrativeRunStatus
    } catch {
      // 拉状态失败 → 回退首次启动
    }
    const rs = data?.runner_status
    if (rs === 'running') {
      addLog(t('narrative.resuming'))
      setPhase(1)
      void fetchDetail()
      poll.start()
      return
    }
    if (rs === 'completed') {
      setPhase(2)
      void fetchDetail()
      onUpdateStatus('completed')
      return
    }
    // idle / interrupted / failed / 无记录 → 启动（或续跑）
    void doStart()
  }, [simulationId, addLog, fetchDetail, poll, onUpdateStatus, doStart, t])

  useEffect(() => {
    if (initedRef.current) return
    initedRef.current = true
    void resumeOrStart()
    return () => poll.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const feedBeats = useMemo(() => beats, [beats])

  return { phase, status, beats: feedBeats, startError, retry: doStart }
}
