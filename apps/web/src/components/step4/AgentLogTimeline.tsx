import { useState } from 'react'

import { cn } from '@/lib/utils'
import type { AgentLogEntry } from '@/lib/step4-types'

// 动作类型 → 展示标签
const ACTION_LABELS: Record<string, string> = {
  report_start: 'Report Start',
  planning_start: 'Planning',
  planning_complete: 'Plan Complete',
  section_start: 'Section Start',
  section_content: 'Section Content',
  section_complete: 'Section Done',
  tool_call: 'Tool Call',
  tool_result: 'Tool Result',
  llm_response: 'LLM Response',
  report_complete: 'Complete',
}

const TOOL_NAMES: Record<string, string> = {
  insight_forge: 'Deep Insight',
  panorama_search: 'Panorama Search',
  interview_agents: 'Agent Interview',
  quick_search: 'Quick Search',
}

/** ReportAgent 执行日志时间线（可展开查看工具参数/结果/LLM 响应）。 */
export function AgentLogTimeline({ logs }: { logs: AgentLogEntry[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  return (
    <div className="space-y-2 border-l border-muted pl-4">
      {logs.map((log, idx) => {
        const key = log.timestamp || String(idx)
        const isMilestone = log.action === 'section_complete' || log.action === 'report_complete'
        const detail = log.details || {}
        const expandable =
          log.action === 'tool_call' || log.action === 'tool_result' || log.action === 'llm_response'
        const isOpen = expanded.has(key)

        return (
          <div key={key} className="relative">
            <span
              className={cn(
                'absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-background',
                isMilestone ? 'bg-green-500' : log.action === 'tool_call' ? 'bg-purple-500' : 'bg-[#FF5722]',
              )}
            />
            <div className="rounded-md border bg-card p-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold">
                  {ACTION_LABELS[log.action] || log.action}
                  {detail.tool_name && (
                    <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[10px] font-normal text-muted-foreground">
                      {TOOL_NAMES[detail.tool_name] || detail.tool_name}
                    </span>
                  )}
                </span>
                {typeof log.elapsed_seconds === 'number' && (
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {log.elapsed_seconds.toFixed(1)}s
                  </span>
                )}
              </div>

              {/* 概要文案 */}
              {detail.message && (
                <p className="mt-1 text-[11px] text-muted-foreground">{detail.message}</p>
              )}
              {log.action === 'planning_complete' && detail.outline && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {detail.outline.sections?.length || 0} sections planned
                </p>
              )}
              {log.action === 'section_start' && log.section_title && (
                <p className="mt-1 text-[11px] text-muted-foreground">{log.section_title}</p>
              )}

              {/* 可展开详情 */}
              {expandable && (
                <>
                  <button
                    onClick={() => toggle(key)}
                    className="mt-1.5 text-[10px] text-[#FF5722] hover:underline"
                  >
                    {isOpen ? '收起' : '展开详情'}
                  </button>
                  {isOpen && (
                    <pre className="mt-1.5 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-[10px] leading-relaxed">
                      {detail.response ||
                        (detail.parameters ? JSON.stringify(detail.parameters, null, 2) : '') ||
                        (detail.result ? JSON.stringify(detail.result, null, 2) : '')}
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
