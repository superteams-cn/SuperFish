import { describe, expect, it } from 'vitest'

import { cn } from './utils'

describe('cn', () => {
  it('合并类名', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('按 tailwind-merge 规则处理冲突（后者覆盖）', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })

  it('忽略假值', () => {
    expect(cn('a', false, undefined, null, 'b')).toBe('a b')
  })
})
