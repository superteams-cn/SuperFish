import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Lightbulb,
  Globe,
  Users,
  Zap,
  BarChart3,
  Database,
  Wrench,
  Pencil,
  Check,
  CheckCircle2,
  type LucideIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { ACCENT_SOFT, STATUS_TEXT } from '@/lib/ui-meta'
import type { AgentLogEntry } from '@/lib/step4-types'
import { ToolResultDisplay } from './ToolResultDisplay'

const ACTION_LABEL_KEYS: Record<string, string> = {
  report_start: 'step4.actionReportStart',
  planning_start: 'step4.actionPlanning',
  planning_complete: 'step4.actionPlanComplete',
  section_start: 'step4.actionSectionStart',
  section_content: 'step4.actionSectionContent',
  section_complete: 'step4.actionSectionDone',
  tool_call: 'step4.actionToolCall',
  tool_result: 'step4.actionToolResult',
  llm_response: 'step4.actionLlmResponse',
  report_complete: 'step4.actionComplete',
}

/** 工具元数据：展示名 i18n key + 图标 + 配色（与旧版 toolConfig 对齐）。 */
const TOOL_META: Record<string, { labelKey: string; Icon: LucideIcon; color: string }> = {
  insight_forge: {
    labelKey: 'step4.toolDeepInsight',
    Icon: Lightbulb,
    color: ACCENT_SOFT.violet,
  },
  panorama_search: {
    labelKey: 'step4.toolPanoramaSearch',
    Icon: Globe,
    color: ACCENT_SOFT.blue,
  },
  interview_agents: {
    labelKey: 'step4.toolAgentInterview',
    Icon: Users,
    color: ACCENT_SOFT.green,
  },
  quick_search: {
    labelKey: 'step4.toolQuickSearch',
    Icon: Zap,
    color: ACCENT_SOFT.orange,
  },
  get_graph_statistics: {
    labelKey: 'step4.toolGraphStats',
    Icon: BarChart3,
    color: ACCENT_SOFT.cyan,
  },
  get_entities_by_type: {
    labelKey: 'step4.toolEntityQuery',
    Icon: Database,
    color: ACCENT_SOFT.pink,
  },
}

function formatClock(ts?: string) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ''
  }
}

/** ReportAgent 执行日志时间线（可展开查看工具参数/结果/LLM 响应）。 */
export function AgentLogTimeline({ logs }: { logs: AgentLogEntry[] }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const endRef = useRef<HTMLDivElement>(null)

  // 新日志到达时，若用户停留在底部附近则自动跟随到底部（不打断向上回看）。
  useEffect(() => {
    const el = endRef.current
    if (!el) return
    const scroller = el.closest('[data-agentlog-scroll], .overflow-y-auto') as HTMLElement | null
    if (scroller) {
      const nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120
      if (!nearBottom) return
    }
    el.scrollIntoView({ block: 'end' })
  }, [logs.length])

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <div className="border-muted space-y-2 border-l pl-4">
      {logs.map((log, idx) => {
        // 同一毫秒可产生多条日志（timestamp 相同），单用 timestamp 当 key 会撞键。
        // 日志流只追加，idx 对既有项稳定，拼上 idx 即唯一又稳定（兼作展开状态键）。
        const key = `${idx}-${log.timestamp ?? ''}`
        const isMilestone = log.action === 'section_complete' || log.action === 'report_complete'
        const detail = log.details || {}
        const toolMeta = detail.tool_name ? TOOL_META[detail.tool_name] : undefined
        // tool_result 走结构化展示组件（含自己的展开/Raw 切换），其余可展开类型仍用通用面板
        const isToolResult = log.action === 'tool_result'
        const expandable = log.action === 'tool_call' || log.action === 'llm_response'
        const isOpen = expanded.has(key)

        return (
          <div key={key} className="relative">
            <span
              className={cn(
                'border-background absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2',
                isMilestone
                  ? 'bg-green-500'
                  : log.action === 'tool_call'
                    ? 'bg-purple-500'
                    : 'bg-brand',
              )}
            />
            <div className="bg-card rounded-md border p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold">
                  {ACTION_LABEL_KEYS[log.action] ? t(ACTION_LABEL_KEYS[log.action]) : log.action}
                  {/* tool_call 在正文用彩色徽章展示工具，这里只为 tool_result 等补一个轻量标签 */}
                  {detail.tool_name && log.action !== 'tool_call' && (
                    <Badge variant="secondary" className="ml-1.5 text-[10px] font-normal">
                      {toolMeta ? t(toolMeta.labelKey) : detail.tool_name}
                    </Badge>
                  )}
                </span>
                <span className="text-muted-foreground flex shrink-0 items-center gap-1.5 font-mono text-[10px]">
                  {log.timestamp && <span>{formatClock(log.timestamp)}</span>}
                  {typeof log.elapsed_seconds === 'number' && (
                    <span>+{log.elapsed_seconds.toFixed(1)}s</span>
                  )}
                </span>
              </div>

              {/* 概要文案 */}
              {detail.message && (
                <p className="text-muted-foreground mt-1 text-[11px]">{detail.message}</p>
              )}

              {/* 报告开始：模拟 id + 需求 */}
              {log.action === 'report_start' && (
                <div className="mt-1 space-y-0.5 text-[11px]">
                  {detail.simulation_id != null && (
                    <div className="flex gap-1.5">
                      <span className="text-muted-foreground">{t('step4.infoSimulation')}</span>
                      <span className="font-mono">{String(detail.simulation_id)}</span>
                    </div>
                  )}
                  {detail.simulation_requirement != null && (
                    <div className="flex gap-1.5">
                      <span className="text-muted-foreground shrink-0">
                        {t('step4.infoRequirement')}
                      </span>
                      <span>{String(detail.simulation_requirement)}</span>
                    </div>
                  )}
                </div>
              )}

              {log.action === 'planning_complete' && detail.outline && (
                <p className="text-muted-foreground mt-1 text-[11px]">
                  {t('step4.sectionsPlanned', { count: detail.outline.sections?.length || 0 })}
                </p>
              )}

              {/* 章节相关：带图标的小标签 */}
              {log.action === 'section_start' && log.section_title && (
                <p className="text-muted-foreground mt-1 text-[11px]">
                  #{log.section_index} {log.section_title}
                </p>
              )}
              {log.action === 'section_content' && log.section_title && (
                <p className="mt-1 flex items-center gap-1.5 text-[11px]">
                  <Pencil className={cn('h-3 w-3', STATUS_TEXT.warning)} />
                  <span>{log.section_title}</span>
                </p>
              )}
              {log.action === 'section_complete' && log.section_title && (
                <p
                  className={cn(
                    'mt-1 flex items-center gap-1.5 text-[11px] font-medium',
                    STATUS_TEXT.success,
                  )}
                >
                  <Check className="h-3 w-3" />
                  <span>{log.section_title}</span>
                </p>
              )}
              {log.action === 'report_complete' && (
                <p
                  className={cn(
                    'mt-1 flex items-center gap-1.5 text-[11px] font-medium',
                    STATUS_TEXT.success,
                  )}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span>{t('step4.reportGenComplete')}</span>
                </p>
              )}

              {/* 工具调用：彩色图标徽章 */}
              {log.action === 'tool_call' && detail.tool_name && (
                <div className="mt-1.5">
                  <span
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold',
                      toolMeta ? toolMeta.color : 'text-muted-foreground bg-muted',
                    )}
                  >
                    {(() => {
                      const Icon = toolMeta?.Icon ?? Wrench
                      return <Icon className="h-3.5 w-3.5" />
                    })()}
                    {toolMeta ? t(toolMeta.labelKey) : detail.tool_name}
                  </span>
                </div>
              )}

              {/* LLM 响应：迭代/工具/最终 元信息 + 最终答案提示 */}
              {log.action === 'llm_response' && (
                <>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {detail.iteration != null && (
                      <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px] font-medium">
                        {t('step4.llmIteration', { n: String(detail.iteration) })}
                      </span>
                    )}
                    <span
                      className={cn(
                        'rounded px-1.5 py-0.5 text-[10px] font-medium',
                        detail.has_tool_calls
                          ? 'bg-purple-500/15 text-purple-600'
                          : 'bg-muted text-muted-foreground',
                      )}
                    >
                      {t('step4.llmTools')}:{' '}
                      {detail.has_tool_calls ? t('common.yes') : t('common.no')}
                    </span>
                    <span
                      className={cn(
                        'rounded px-1.5 py-0.5 text-[10px] font-medium',
                        detail.has_final_answer
                          ? 'bg-green-500/15 text-green-600'
                          : 'bg-muted text-muted-foreground',
                      )}
                    >
                      {t('step4.llmFinal')}:{' '}
                      {detail.has_final_answer ? t('common.yes') : t('common.no')}
                    </span>
                  </div>
                  {detail.has_final_answer && (
                    <p
                      className={cn(
                        'mt-1 flex items-center gap-1.5 text-[11px]',
                        STATUS_TEXT.success,
                      )}
                    >
                      <Check className="h-3 w-3" />
                      <span>{t('step4.llmFinalHint', { title: log.section_title || '' })}</span>
                    </p>
                  )}
                </>
              )}

              {/* 工具结果：按工具类型结构化展示，JSON 兜底 */}
              {isToolResult && (
                <ToolResultDisplay
                  toolName={detail.tool_name}
                  result={detail.result}
                  resultLength={detail.result_length}
                />
              )}

              {/* 其余可展开详情（工具调用参数 / LLM 响应） */}
              {expandable && (detail.response || detail.parameters) && (
                <>
                  <Button
                    variant="link"
                    size="sm"
                    onClick={() => toggle(key)}
                    className="text-brand mt-1 h-auto p-0 text-[10px]"
                  >
                    {isOpen ? t('step4.collapseDetail') : t('step4.expandDetail')}
                  </Button>
                  {isOpen && (
                    <pre className="bg-muted mt-1.5 max-h-60 overflow-auto whitespace-pre-wrap rounded p-2 text-[10px] leading-relaxed">
                      {detail.response ||
                        (detail.parameters ? JSON.stringify(detail.parameters, null, 2) : '')}
                    </pre>
                  )}
                </>
              )}
            </div>
          </div>
        )
      })}
      <div ref={endRef} />
    </div>
  )
}
