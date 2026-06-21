import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useDedupedLog } from './useDedupedLog'

describe('useDedupedLog', () => {
  it('首个 key 视为新；重复的同值返回 false', () => {
    const { result } = renderHook(() => useDedupedLog<string>())
    expect(result.current.isNew('a')).toBe(true)
    expect(result.current.isNew('a')).toBe(false)
  })

  it('值变化后再次返回 true', () => {
    const { result } = renderHook(() => useDedupedLog<string>())
    expect(result.current.isNew('a')).toBe(true)
    expect(result.current.isNew('b')).toBe(true)
    expect(result.current.isNew('b')).toBe(false)
    expect(result.current.isNew('a')).toBe(true) // 与「上一个」比较，非历史去重
  })

  it('支持数字等其他可比较类型', () => {
    const { result } = renderHook(() => useDedupedLog<number>(0))
    expect(result.current.isNew(0)).toBe(false) // 与初始值相同
    expect(result.current.isNew(1)).toBe(true)
    expect(result.current.isNew(1)).toBe(false)
  })

  it('reset 后回到初始值，下一个 key 重新算新', () => {
    const { result } = renderHook(() => useDedupedLog<string>())
    expect(result.current.isNew('a')).toBe(true)
    result.current.reset()
    expect(result.current.isNew('a')).toBe(true)
  })

  // 不变量：返回的 handle 跨渲染引用恒定。调用方常把它放进 useCallback/useEffect 依赖，
  // 若退回未 memo 版本（每渲染返回新对象），依赖链会每渲染失效 → 渲染循环/无效重算。
  it('返回稳定 handle：跨渲染引用不变（含初始值参数不变时）', () => {
    const { result, rerender } = renderHook(() => useDedupedLog<string>('init'))
    const first = result.current
    rerender()
    rerender()
    expect(result.current).toBe(first)
    expect(result.current.isNew).toBe(first.isNew)
    expect(result.current.reset).toBe(first.reset)
  })
})
