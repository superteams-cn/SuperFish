import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FileText, History, Loader2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { getSimulationHistory } from '@/lib/api/simulation'
import { deleteProject } from '@/lib/api/graph'
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

interface HistoryDatabaseProps {
  /** 历史项目加载完成后回调（用于首页决定是否显示"滚动到历史"按钮）。 */
  onHasProjects?: (hasProjects: boolean) => void
}

/** 首页历史库：展示历史模拟项目卡片，点击查看详情并回放到对应步骤。 */
export function HistoryDatabase({ onHasProjects }: HistoryDatabaseProps = {}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<HistoryProject[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<HistoryProject | null>(null)
  // 待确认删除的项目（null 表示无）
  const [pendingDelete, setPendingDelete] = useState<HistoryProject | null>(null)
  const [deleting, setDeleting] = useState(false)
  // 进入视口前卡片处于堆叠/淡入态，进入后展开为网格
  const [revealed, setRevealed] = useState(false)
  const loadedRef = useRef(false)
  const sectionRef = useRef<HTMLElement | null>(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const res = await getSimulationHistory(20)
      const list = res.success ? res.data || [] : []
      setProjects(list)
      onHasProjects?.(list.length > 0)
    } catch (err) {
      console.error('加载历史项目失败:', err)
      setProjects([])
      onHasProjects?.(false)
    } finally {
      setLoading(false)
    }
  }, [onHasProjects])

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    void load()
  }, [load])

  // 删除项目（连同图谱/模拟/报告）。历史记录以模拟为单位，但删除作用于其所属项目。
  const confirmDelete = async () => {
    const p = pendingDelete
    if (!p) return
    if (!p.project_id) {
      toast.error(t('history.noProjectToDelete'))
      setPendingDelete(null)
      return
    }
    try {
      setDeleting(true)
      const res = await deleteProject(p.project_id)
      if (res.success) {
        toast.success(t('history.deleteSuccess'))
        // 同项目下的其它模拟一并消失，直接按 project_id 过滤
        setProjects((prev) => prev.filter((x) => x.project_id !== p.project_id))
        if (selected?.project_id === p.project_id) setSelected(null)
        setPendingDelete(null)
      } else {
        toast.error(res.error || t('history.deleteFailed'))
      }
    } catch {
      toast.error(t('history.deleteFailed'))
    } finally {
      setDeleting(false)
    }
  }

  // 进入视口时触发展开动画（一次性，避免来回滚动反复抖动）
  useEffect(() => {
    if (loading || projects.length === 0) return
    const el = sectionRef.current
    if (!el) return

    // 尊重用户的“减少动效”偏好：直接展开，不做过渡
    const reduceMotion =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduceMotion) {
      setRevealed(true)
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setRevealed(true)
            observer.disconnect()
          }
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -80px 0px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [loading, projects.length])

  // 预测进展 → 人话状态徽章（不再暴露轮数等内部概念）
  const statusInfo = (p: HistoryProject) => {
    const total = p.total_rounds || 0
    const cur = p.current_round || 0
    if (p.report_id || (total > 0 && cur >= total)) {
      return {
        label: t('history.done'),
        cls: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
      }
    }
    if (p.simulation_id && total > 0) {
      return {
        label: t('history.inProgress'),
        cls: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
      }
    }
    return { label: t('history.notStarted'), cls: 'bg-muted text-muted-foreground' }
  }

  if (loading) {
    return (
      <div className="text-muted-foreground flex items-center justify-center gap-2 py-12 text-sm">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('history.loadingText')}
      </div>
    )
  }

  if (projects.length === 0) return null

  return (
    <section id="history-section" ref={sectionRef} className="mt-12 scroll-mt-6">
      <div className="mb-5 flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white shadow-md">
          <History className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold leading-tight">{t('history.title')}</h2>
          <p className="text-muted-foreground text-xs">
            {t('history.predictionCount', { count: projects.length })}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((p, index) => {
          // 折叠态：以网格中心为基准做扇形堆叠（左右偏移 + 旋转 + 缩放 + 下沉）
          const centerIndex = (projects.length - 1) / 2
          const offset = index - centerIndex
          const stackStyle: React.CSSProperties = {
            transform: `translate3d(${offset * 22}px, ${24 + Math.abs(offset) * 6}px, 0) rotate(${offset * 2.5}deg) scale(0.92)`,
            opacity: 0,
          }
          const gridStyle: React.CSSProperties = {
            transform: 'translate3d(0, 0, 0) rotate(0deg) scale(1)',
            opacity: 1,
          }
          // 进场轻微错峰，营造“逐张归位”的观感；上限避免后排卡片等待过久
          const delay = revealed ? `${Math.min(index, 11) * 45}ms` : '0ms'

          return (
            <div
              key={p.simulation_id || p.project_id}
              role="button"
              tabIndex={0}
              onClick={() => setSelected(p)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setSelected(p)
                }
              }}
              style={{
                ...(revealed ? gridStyle : stackStyle),
                transitionDelay: delay,
                willChange: 'transform, opacity',
              }}
              className={cn(
                'bg-card focus-visible:ring-ring group relative isolate cursor-pointer overflow-hidden rounded-2xl border p-4 text-left backdrop-blur-xl focus-visible:outline-none focus-visible:ring-2',
                'transition-[transform,opacity,box-shadow,border-color] duration-700 ease-[cubic-bezier(0.23,1,0.32,1)]',
                'hover:border-brand hover:-translate-y-1 hover:shadow-lg',
                'motion-reduce:transition-none',
              )}
            >
              {/* 取景框风格角标 */}
              <span className="border-foreground/40 pointer-events-none absolute left-1.5 top-1.5 h-2 w-2 border-l-[1.5px] border-t-[1.5px] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />

              {/* 删除按钮（hover 显隐，仅在有关联项目时可用） */}
              <button
                type="button"
                aria-label={t('history.deleteProject')}
                title={p.project_id ? t('history.deleteProject') : t('history.noProjectToDelete')}
                disabled={!p.project_id}
                onClick={(e) => {
                  e.stopPropagation()
                  setPendingDelete(p)
                }}
                className="bg-background/90 text-muted-foreground hover:text-destructive hover:border-destructive absolute right-1.5 top-1.5 z-10 grid h-6 w-6 place-items-center rounded-md border opacity-0 transition-opacity duration-200 disabled:cursor-not-allowed disabled:opacity-0 group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>

              <div className="mb-3 flex items-center justify-between gap-2">
                {(() => {
                  const s = statusInfo(p)
                  return (
                    <span className={cn('rounded-full px-2.5 py-0.5 text-xs font-medium', s.cls)}>
                      {s.label}
                    </span>
                  )
                })()}
                <span className="text-muted-foreground shrink-0 text-xs">
                  {formatDateTime(p.created_at)}
                </span>
              </div>

              <h3 className="group-hover:text-brand mb-2 line-clamp-2 font-semibold transition-colors">
                {truncate(p.simulation_requirement, 40) || t('history.untitledSimulation')}
              </h3>

              <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
                <FileText className="h-3.5 w-3.5 shrink-0" />
                <span>
                  {p.files && p.files.length > 0
                    ? t('history.fileCount', { count: p.files.length })
                    : t('history.noFiles')}
                </span>
              </div>

              {/* 底部强调线（hover 时展开） */}
              <span className="bg-brand absolute bottom-0 left-0 h-0.5 w-0 transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] group-hover:w-full" />
            </div>
          )
        })}
      </div>

      {/* 详情模态 */}
      <Dialog open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent>
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="text-base">
                  {truncate(selected.simulation_requirement, 30) || t('history.untitledSimulation')}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <div className="text-muted-foreground mb-1 text-[10px] font-semibold uppercase">
                    {t('history.simRequirement')}
                  </div>
                  <p className="text-sm">{selected.simulation_requirement || t('common.none')}</p>
                </div>
                {!!selected.files?.length && (
                  <div>
                    <div className="text-muted-foreground mb-1 text-[10px] font-semibold uppercase">
                      {t('history.relatedFiles')}
                    </div>
                    <div className="space-y-1">
                      {selected.files.map((f, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm">
                          <Badge variant="secondary" className="text-[10px]">
                            {fileExt(f.filename)}
                          </Badge>
                          <span className="truncate">{f.filename}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-3 gap-2 border-t pt-4">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!selected.project_id}
                  onClick={() => navigate(`/process/${selected.project_id}`)}
                >
                  {t('history.step1Button')}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!selected.simulation_id}
                  onClick={() => navigate(`/simulation/${selected.simulation_id}`)}
                >
                  {t('history.step2Button')}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!selected.report_id}
                  onClick={() => navigate(`/report/${selected.report_id}`)}
                >
                  {t('history.step4Button')}
                </Button>
              </div>
              <Button
                variant="ghost"
                size="sm"
                disabled={!selected.project_id}
                onClick={() => {
                  // 先关详情弹窗，避免两个 modal 叠加导致确认弹窗无法交互
                  const target = selected
                  setSelected(null)
                  setPendingDelete(target)
                }}
                className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 w-full gap-1.5"
              >
                <Trash2 className="h-4 w-4" />
                {t('history.deleteProject')}
              </Button>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <Dialog
        open={!!pendingDelete}
        onOpenChange={(open) => !open && !deleting && setPendingDelete(null)}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('history.deleteConfirmTitle')}</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">{t('history.deleteConfirmDesc')}</p>
          {pendingDelete && (
            <p className="bg-muted/50 truncate rounded-md px-3 py-2 text-sm">
              {truncate(pendingDelete.simulation_requirement, 36) ||
                t('history.untitledSimulation')}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={deleting}
              onClick={() => setPendingDelete(null)}
            >
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={deleting}
              onClick={confirmDelete}
              className="gap-1.5"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              {t('history.deleteProject')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  )
}
