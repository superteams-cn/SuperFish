import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import type { SystemLog } from '@/lib/process-types'

interface SystemLogTerminalProps {
  logs: SystemLog[]
  /** 右上角标识（如项目ID / 模拟ID） */
  badge?: string
}

/** 黑底终端风格的系统日志面板，自动滚动到底部。Step1/Step2 等复用。 */
export function SystemLogTerminal({ logs, badge }: SystemLogTerminalProps) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [logs.length])

  return (
    <div className="flex-shrink-0 border-t border-zinc-800 bg-black p-4 font-mono text-zinc-300">
      <div className="mb-2 flex justify-between border-b border-zinc-700 pb-2 text-[10px] text-zinc-500">
        <span>{t('common.systemDashboard')}</span>
        <span>{badge || 'NO_ID'}</span>
      </div>
      <div ref={ref} className="flex h-20 flex-col gap-1 overflow-y-auto pr-1">
        {logs.map((log, idx) => (
          <div key={idx} className="flex gap-3 text-[11px] leading-relaxed">
            <span className="min-w-[75px] text-zinc-600">{log.time}</span>
            <span className="break-all text-zinc-300">{log.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
