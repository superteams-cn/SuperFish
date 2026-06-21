import { useCallback, useEffect, useMemo, useRef } from 'react'

interface UsePollingOptions {
  /** 启动时是否立即执行一次回调（默认 false，首帧在 intervalMs 后）。 */
  immediate?: boolean
  /** 连续失败时指数退避的间隔上限（毫秒，默认 30000）。 */
  maxBackoffMs?: number
}

interface PollingHandle {
  /** 启动轮询。重复调用幂等（不会叠加定时器）。 */
  start: () => void
  /** 停止轮询（幂等）。 */
  stop: () => void
  /** 当前是否在轮询中。 */
  isActive: () => boolean
}

/**
 * 命令式轮询：以 intervalMs 为基准周期调用最新的 callback，组件卸载时自动清理。
 *
 * 关键设计（防止「请求只发不回、越堆越多」把浏览器连接池打爆）：
 * - **无重叠自调度**：用递归 setTimeout 而非 setInterval —— 必须等上一次 callback
 *   settle（resolve/reject）后才安排下一次。任一时刻同一 poller 最多 1 个在途请求，
 *   服务端慢/挂时请求不再累积。
 * - **失败指数退避**：callback 抛错时按 interval·2^n 拉长间隔（封顶 maxBackoffMs），
 *   成功即归零。服务端短暂不可用不会变成定速猛冲的请求风暴。
 * - callback 始终取最新引用（存 ref），无需放进依赖、也不会读到过期闭包。
 */
export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  options: UsePollingOptions = {},
): PollingHandle {
  const { immediate = false, maxBackoffMs = 30000 } = options
  const callbackRef = useRef(callback)
  const intervalRef = useRef(intervalMs)
  const maxBackoffRef = useRef(maxBackoffMs)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const stoppedRef = useRef(true)
  const inFlightRef = useRef(false)
  const failuresRef = useRef(0)

  // 始终指向最新回调/配置，避免定时器闭包读到过期的 state/props
  useEffect(() => {
    callbackRef.current = callback
  }, [callback])
  useEffect(() => {
    intervalRef.current = intervalMs
  }, [intervalMs])
  useEffect(() => {
    maxBackoffRef.current = maxBackoffMs
  }, [maxBackoffMs])

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  // 执行一次回调，settle 后再安排下一次（无重叠）；失败则退避。
  const tick = useCallback(async () => {
    if (stoppedRef.current || inFlightRef.current) return
    inFlightRef.current = true
    try {
      await callbackRef.current()
      failuresRef.current = 0
    } catch {
      failuresRef.current += 1
    } finally {
      inFlightRef.current = false
    }
    if (stoppedRef.current) return
    const delay =
      failuresRef.current > 0
        ? Math.min(intervalRef.current * 2 ** failuresRef.current, maxBackoffRef.current)
        : intervalRef.current
    clearTimer()
    timerRef.current = setTimeout(() => void tick(), delay)
  }, [clearTimer])

  const start = useCallback(() => {
    stoppedRef.current = false
    failuresRef.current = 0
    clearTimer()
    if (immediate) {
      void tick()
    } else {
      timerRef.current = setTimeout(() => void tick(), intervalRef.current)
    }
  }, [clearTimer, immediate, tick])

  const stop = useCallback(() => {
    stoppedRef.current = true
    clearTimer()
  }, [clearTimer])

  const isActive = useCallback(() => !stoppedRef.current, [])

  // 卸载自动清理
  useEffect(() => stop, [stop])

  // 返回稳定的 handle 对象：start/stop/isActive 均为稳定 useCallback，故该对象一次成型、
  // 跨渲染不变。这一点是正确性的关键 —— 调用方常把 start/stop 放进自身 useCallback /
  // useEffect 依赖；若每次渲染都返回新对象，会让那些依赖链每渲染失效，进而触发
  // 「effect 每渲染重跑 → 重置状态 + immediate 重新发请求」的渲染死循环（请求风暴）。
  return useMemo(() => ({ start, stop, isActive }), [start, stop, isActive])
}
