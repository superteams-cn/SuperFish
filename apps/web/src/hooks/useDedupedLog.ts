import { useCallback, useMemo, useRef } from 'react'

interface Deduper<T> {
  /** 若 key 与上次不同则返回 true 并记下它；相同返回 false。用于「同一内容不重复打日志」。 */
  isNew: (key: T) => boolean
  /** 重置内部记忆（如重新开始一轮轮询前）。 */
  reset: () => void
}

/**
 * 单值去重器：记住上一次见过的 key，仅当 key 变化时 isNew 返回 true。
 *
 * 替代现有轮询里散落的 `lastMsg.current` / `lastProfileCount.current` /
 * `lastConfigStage.current` / `buildMsgRef.current` 等手写「记上次值再比较」样板。
 * 每个独立的去重维度各持一个本 hook 实例。
 *
 * @param initial 初始已见值（默认 undefined，即任何首个 key 都算「新」）。
 */
export function useDedupedLog<T>(initial?: T): Deduper<T> {
  const lastRef = useRef<T | undefined>(initial)

  const isNew = useCallback((key: T): boolean => {
    if (key === lastRef.current) return false
    lastRef.current = key
    return true
  }, [])

  const reset = useCallback(() => {
    lastRef.current = initial
  }, [initial])

  // 返回稳定 handle：与 usePolling 同理，调用方常把 deduper 放进 useCallback/useEffect
  // 依赖；若每渲染返回新对象会让那些依赖链每渲染失效，埋下渲染循环/无效重算的隐患。
  return useMemo(() => ({ isNew, reset }), [isNew, reset])
}
