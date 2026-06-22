import { useCallback, useEffect, useState } from 'react'

import { getProjectQuota, type ProjectQuota } from '@/lib/api/graph'

interface Options {
  /** 为 false 时不拉取（如未登录），quota 保持 null。默认 true。 */
  enabled?: boolean
  /** 轮询间隔（毫秒）。传入则定时刷新。 */
  pollMs?: number
}

/**
 * 项目名额：开始预测前显式告知名额占用，并在已满时拦截。
 *
 * 与 useSimulationQuota 同形：返回快照 + refresh（返回最新值，供点击时做权威校验，
 * 避免用展示用旧值放行）。拉取失败返回 null，调用方降级为不拦截（后端仍有 403 兜底）。
 */
export function useProjectQuota({ enabled = true, pollMs }: Options = {}) {
  const [quota, setQuota] = useState<ProjectQuota | null>(null)

  const refresh = useCallback(async (): Promise<ProjectQuota | null> => {
    if (!enabled) return null
    try {
      const res = await getProjectQuota()
      const data = res.success ? (res.data ?? null) : null
      setQuota(data)
      return data
    } catch {
      setQuota(null)
      return null
    }
  }, [enabled])

  useEffect(() => {
    if (!enabled) {
      setQuota(null)
      return
    }
    void refresh()
    if (!pollMs) return
    const id = setInterval(() => void refresh(), pollMs)
    return () => clearInterval(id)
  }, [enabled, pollMs, refresh])

  return { quota, refresh }
}
