import { useCallback, useEffect, useState } from 'react'

import { getSimulationQuota, type SimulationQuota } from '@/lib/api/simulation'

/**
 * 并发推演配额：进入推演前显式告知名额占用，并在已满时拦截。
 *
 * 返回当前配额快照与 refresh（返回最新值，供「点击进入推演」时做权威的实时校验，
 * 避免用展示用的旧值放行）。任一拉取失败返回 null，调用方据此降级为不拦截（最终仍有
 * 后端 /start 兜底）。
 */
export function useSimulationQuota() {
  const [quota, setQuota] = useState<SimulationQuota | null>(null)

  const refresh = useCallback(async (): Promise<SimulationQuota | null> => {
    try {
      const res = await getSimulationQuota()
      const data = res.success ? (res.data ?? null) : null
      setQuota(data)
      return data
    } catch {
      setQuota(null)
      return null
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { quota, refresh }
}
