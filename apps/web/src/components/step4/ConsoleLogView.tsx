import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

/** 控制台日志级别着色（ERROR/错误 → 红，WARNING/警告 → 琥珀）。 */
function consoleLevelClass(line: string) {
  if (line.includes('ERROR') || line.includes('错误')) return 'text-red-400'
  if (line.includes('WARNING') || line.includes('警告')) return 'text-amber-400'
  return ''
}

/** 终端风格控制台输出：级别着色 + 新日志自动滚到底部。 */
export function ConsoleLogView({ logs, emptyText }: { logs: string[]; emptyText: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (el) el.scrollTop = el.scrollHeight
  }, [logs.length])
  return (
    <div
      ref={ref}
      className="h-full overflow-y-auto bg-black p-4 font-mono text-[11px] text-zinc-300"
    >
      {logs.length === 0 && <span className="text-zinc-600">{emptyText}</span>}
      {logs.map((line, idx) => (
        <div key={idx} className={cn('break-all leading-relaxed', consoleLevelClass(line))}>
          {line}
        </div>
      ))}
    </div>
  )
}
