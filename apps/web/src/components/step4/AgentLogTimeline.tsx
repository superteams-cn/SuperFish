import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
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

const TOOL_NAME_KEYS: Record<string, string> = {
  insight_forge: 'step4.toolDeepInsight',
  panorama_search: 'step4.toolPanoramaSearch',
  interview_agents: 'step4.toolAgentInterview',
  quick_search: 'step4.toolQuickSearch',
}

/** ReportAgent 执行日志时间线（可展开查看工具参数/结果/LLM 响应）。 */
export function AgentLogTimeline({ logs }: { logs: AgentLogEntry[] }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

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
        const key = log.timestamp || String(idx)
        const isMilestone = log.action === 'section_complete' || log.action === 'report_complete'
        const detail = log.details || {}
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
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold">
                  {ACTION_LABEL_KEYS[log.action] ? t(ACTION_LABEL_KEYS[log.action]) : log.action}
                  {detail.tool_name && (
                    <Badge variant="secondary" className="ml-1.5 text-[10px] font-normal">
                      {TOOL_NAME_KEYS[detail.tool_name]
                        ? t(TOOL_NAME_KEYS[detail.tool_name])
                        : detail.tool_name}
                    </Badge>
                  )}
                </span>
                {typeof log.elapsed_seconds === 'number' && (
                  <span className="text-muted-foreground font-mono text-[10px]">
                    {log.elapsed_seconds.toFixed(1)}s
                  </span>
                )}
              </div>

              {/* 概要文案 */}
              {detail.message && (
                <p className="text-muted-foreground mt-1 text-[11px]">{detail.message}</p>
              )}
              {log.action === 'planning_complete' && detail.outline && (
                <p className="text-muted-foreground mt-1 text-[11px]">
                  {t('step4.sectionsPlanned', { count: detail.outline.sections?.length || 0 })}
                </p>
              )}
              {log.action === 'section_start' && log.section_title && (
                <p className="text-muted-foreground mt-1 text-[11px]">{log.section_title}</p>
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
              {expandable && (
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
    </div>
  )
}
