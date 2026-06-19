import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  parseInsightForge,
  parseInterview,
  parsePanorama,
  parseQuickSearch,
  toResultText,
} from '@/lib/step4-parsers'
import { InsightDisplay } from './InsightDisplay'
import { InterviewDisplay } from './InterviewDisplay'
import { PanoramaDisplay } from './PanoramaDisplay'
import { QuickSearchDisplay } from './QuickSearchDisplay'

const STRUCTURED_TOOLS = new Set([
  'insight_forge',
  'panorama_search',
  'interview_agents',
  'quick_search',
])

/** 工具结果分流渲染：按工具类型走专用结构化组件，未知工具/解析失败兜底为原始文本(JSON)。 */
export function ToolResultDisplay({
  toolName,
  result,
  resultLength,
}: {
  toolName?: string
  result: unknown
  resultLength?: number
}) {
  const { t } = useTranslation()
  const [raw, setRaw] = useState(false)
  const text = toResultText(result)
  const structured = !!toolName && STRUCTURED_TOOLS.has(toolName)

  const rawBlock = (
    <pre className="bg-muted mt-1.5 max-h-60 overflow-auto whitespace-pre-wrap rounded p-2 text-[10px] leading-relaxed">
      {text}
    </pre>
  )

  if (!structured) return rawBlock

  return (
    <div>
      {raw ? (
        rawBlock
      ) : (
        <div className="bg-card mt-1.5 rounded-md border p-2.5">
          {toolName === 'insight_forge' && (
            <InsightDisplay result={parseInsightForge(text)} resultLength={resultLength} />
          )}
          {toolName === 'panorama_search' && (
            <PanoramaDisplay result={parsePanorama(text)} resultLength={resultLength} />
          )}
          {toolName === 'interview_agents' && (
            <InterviewDisplay result={parseInterview(text)} resultLength={resultLength} />
          )}
          {toolName === 'quick_search' && (
            <QuickSearchDisplay result={parseQuickSearch(text)} resultLength={resultLength} />
          )}
        </div>
      )}
      <Button
        variant="link"
        size="sm"
        className="text-brand mt-1 h-auto p-0 text-[10px]"
        onClick={() => setRaw((v) => !v)}
      >
        {raw ? t('step4.structuredView') : t('step4.rawOutput')}
      </Button>
    </div>
  )
}
