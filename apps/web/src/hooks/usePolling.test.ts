import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { usePolling } from './usePolling'

// 新实现「等回调 settle 后再排下一次」（无重叠自调度），故推进需用异步定时器并
// flush 微任务，否则 await 之后的重排不会发生。
const flush = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)))

describe('usePolling', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('不 start 时不调用回调', async () => {
    const cb = vi.fn()
    renderHook(() => usePolling(cb, 1000))
    await flush(5000)
    expect(cb).not.toHaveBeenCalled()
  })

  it('start 后按间隔周期调用；immediate=false 首帧在间隔之后', async () => {
    const cb = vi.fn()
    const { result } = renderHook(() => usePolling(cb, 1000))
    act(() => result.current.start())
    expect(cb).toHaveBeenCalledTimes(0) // 非 immediate：尚未到第一帧
    await flush(1000)
    expect(cb).toHaveBeenCalledTimes(1)
    await flush(2000)
    expect(cb).toHaveBeenCalledTimes(3)
  })

  it('immediate=true 时 start 立即执行一次', async () => {
    const cb = vi.fn()
    const { result } = renderHook(() => usePolling(cb, 1000, { immediate: true }))
    act(() => result.current.start())
    expect(cb).toHaveBeenCalledTimes(1)
    await flush(1000)
    expect(cb).toHaveBeenCalledTimes(2)
  })

  it('stop 后不再调用', async () => {
    const cb = vi.fn()
    const { result } = renderHook(() => usePolling(cb, 1000))
    act(() => result.current.start())
    await flush(1000)
    expect(cb).toHaveBeenCalledTimes(1)
    act(() => result.current.stop())
    await flush(5000)
    expect(cb).toHaveBeenCalledTimes(1)
  })

  it('重复 start 不叠加定时器', async () => {
    const cb = vi.fn()
    const { result } = renderHook(() => usePolling(cb, 1000))
    act(() => result.current.start())
    act(() => result.current.start())
    act(() => result.current.start())
    await flush(1000)
    expect(cb).toHaveBeenCalledTimes(1)
  })

  it('始终调用最新的回调（不读过期闭包）', async () => {
    const first = vi.fn()
    const second = vi.fn()
    const { result, rerender } = renderHook(({ cb }) => usePolling(cb, 1000), {
      initialProps: { cb: first },
    })
    act(() => result.current.start())
    rerender({ cb: second })
    await flush(1000)
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })

  it('卸载时自动清理定时器', async () => {
    const cb = vi.fn()
    const { result, unmount } = renderHook(() => usePolling(cb, 1000))
    act(() => result.current.start())
    unmount()
    await flush(5000)
    expect(cb).not.toHaveBeenCalled()
  })

  it('isActive 反映轮询状态', () => {
    const { result } = renderHook(() => usePolling(() => {}, 1000))
    expect(result.current.isActive()).toBe(false)
    act(() => result.current.start())
    expect(result.current.isActive()).toBe(true)
    act(() => result.current.stop())
    expect(result.current.isActive()).toBe(false)
  })

  it('无重叠：上一次未 settle 不会重复触发', async () => {
    let resolve!: () => void
    const cb = vi.fn(() => new Promise<void>((r) => (resolve = r)))
    const { result } = renderHook(() => usePolling(cb, 1000, { immediate: true }))
    act(() => result.current.start())
    expect(cb).toHaveBeenCalledTimes(1) // 首次在途
    await flush(5000)
    expect(cb).toHaveBeenCalledTimes(1) // 在途期间不再触发
    await act(async () => {
      resolve()
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(cb).toHaveBeenCalledTimes(2) // settle 后下一帧才继续
  })

  // 不变量：返回的 handle 跨渲染引用恒定（即使每次传入新的 callback）。调用方常把
  // start/stop 放进 useCallback/useEffect 依赖，若退回未 memo 版本（每渲染返回新对象），
  // 依赖链会每渲染失效 → 「effect 每渲染重跑 + immediate 重发请求」的渲染循环。
  it('返回稳定 handle：跨渲染引用不变（含 callback 每次变化）', () => {
    const { result, rerender } = renderHook(({ cb }) => usePolling(cb, 1000), {
      initialProps: { cb: () => {} },
    })
    const first = result.current
    rerender({ cb: () => {} }) // 新 callback 引用
    rerender({ cb: () => {} })
    expect(result.current).toBe(first)
    expect(result.current.start).toBe(first.start)
    expect(result.current.stop).toBe(first.stop)
  })

  it('失败时指数退避（间隔随连续失败拉长）', async () => {
    const cb = vi.fn(() => Promise.reject(new Error('boom')))
    const { result } = renderHook(() => usePolling(cb, 1000, { immediate: true }))
    act(() => result.current.start())
    await flush(0)
    expect(cb).toHaveBeenCalledTimes(1) // immediate 首帧（失败）
    await flush(1000)
    expect(cb).toHaveBeenCalledTimes(1) // 退避到 2000ms：1000ms 时未到
    await flush(1000)
    expect(cb).toHaveBeenCalledTimes(2) // 2000ms 第二帧
  })
})
