import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2, X } from 'lucide-react'

import { getSimulationHistory } from '@/lib/api/simulation'
import { cn } from '@/lib/utils'

interface HistoryProject {
  simulation_id?: string
  project_id?: string
  report_id?: string
  simulation_requirement?: string
  files?: { filename: string }[]
  created_at?: string
  current_round?: number
  total_rounds?: number
}

function formatSimId(id?: string) {
  if (!id) return 'SIM_UNKNOWN'
  return `SIM_${id.replace('sim_', '').slice(0, 6).toUpperCase()}`
}
function fileExt(name?: string) {
  return name?.split('.').pop()?.toUpperCase() || 'FILE'
}
function truncate(text: string | undefined, max: number) {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '...' : text
}
function formatDateTime(s?: string) {
  if (!s) return ''
  try {
    const d = new Date(s)
    return `${d.toISOString().slice(0, 10)} ${d.getHours().toString().padStart(2, '0')}:${d
      .getMinutes()
      .toString()
      .padStart(2, '0')}`
  } catch {
    return ''
  }
}

/** 首页历史库：展示历史模拟项目卡片，点击查看详情并回放到对应步骤。 */
export function HistoryDatabase() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<HistoryProject[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<HistoryProject | null>(null)
  const loadedRef = useRef(false)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const res = await getSimulationHistory(20)
      if (res.success) setProjects(res.data || [])
    } catch (err) {
      console.error('加载历史项目失败:', err)
      setProjects([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    void load()
  }, [load])

  const rounds = (p: HistoryProject) => {
    const total = p.total_rounds || 0
    if (total === 0) return t('history.notStarted')
    return t('history.roundsProgress', { current: p.current_round || 0, total })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('history.loadingText')}
      </div>
    )
  }

  if (projects.length === 0) return null

  return (
    <section className="mt-12">
      <div className="mb-4 flex items-center gap-3">
        <div className="h-px flex-1 bg-border" />
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t('history.title')}
        </span>
        <div className="h-px flex-1 bg-border" />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((p) => (
          <button
            key={p.simulation_id}
            onClick={() => setSelected(p)}
            className="rounded-lg border bg-card p-4 text-left transition hover:border-[#FF5722] hover:shadow-md"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-muted-foreground">
                {formatSimId(p.simulation_id)}
              </span>
              <div className="flex gap-1 text-xs">
                <span className={p.project_id ? 'text-[#FF5722]' : 'text-muted-foreground/40'}>◇</span>
                <span className="text-[#FF5722]">◈</span>
                <span className={p.report_id ? 'text-[#FF5722]' : 'text-muted-foreground/40'}>◆</span>
              </div>
            </div>
            <h3 className="mb-1 truncate text-sm font-semibold">
              {truncate(p.simulation_requirement, 20) || t('history.untitledSimulation')}
            </h3>
            <p className="mb-3 line-clamp-2 text-xs text-muted-foreground">
              {truncate(p.simulation_requirement, 55)}
            </p>
            <div className="flex items-center justify-between text-[10px] text-muted-foreground">
              <span>{formatDateTime(p.created_at)}</span>
              <span>{rounds(p)}</span>
            </div>
          </button>
        ))}
      </div>

      {/* 详情模态 */}
      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelected(null)
          }}
        >
          <div className="w-full max-w-lg rounded-lg border bg-background shadow-xl">
            <div className="flex items-center justify-between border-b px-5 py-4">
              <span className="font-mono text-sm font-bold">{formatSimId(selected.simulation_id)}</span>
              <button onClick={() => setSelected(null)} className="text-muted-foreground hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4 p-5">
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">
                  {t('history.simRequirement')}
                </div>
                <p className="text-sm">{selected.simulation_requirement || t('common.none')}</p>
              </div>
              {!!selected.files?.length && (
                <div>
                  <div className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">
                    {t('history.relatedFiles')}
                  </div>
                  <div className="space-y-1">
                    {selected.files.map((f, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px]">{fileExt(f.filename)}</span>
                        <span className="truncate">{f.filename}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2 border-t p-4">
              <ReplayBtn
                disabled={!selected.project_id}
                label={t('history.step1Button')}
                onClick={() => navigate(`/process/${selected.project_id}`)}
              />
              <ReplayBtn
                disabled={!selected.simulation_id}
                label={t('history.step2Button')}
                onClick={() => navigate(`/simulation/${selected.simulation_id}`)}
              />
              <ReplayBtn
                disabled={!selected.report_id}
                label={t('history.step4Button')}
                onClick={() => navigate(`/report/${selected.report_id}`)}
              />
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function ReplayBtn({ disabled, label, onClick }: { disabled: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded border py-2 text-xs font-medium transition',
        disabled ? 'cursor-not-allowed opacity-40' : 'hover:bg-accent',
      )}
    >
      {label}
    </button>
  )
}
