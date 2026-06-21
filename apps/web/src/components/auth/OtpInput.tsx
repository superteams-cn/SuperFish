import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from 'react'

import { cn } from '@/lib/utils'

interface OtpInputProps {
  value: string
  onChange: (value: string) => void
  length?: number
  focusOnMount?: boolean
  disabled?: boolean
  /** 填满 length 位时回调（便于自动提交） */
  onComplete?: (value: string) => void
}

/** 分格验证码输入：length 个独立数字框，支持自动前进/退格/方向键/整段粘贴。 */
export function OtpInput({
  value,
  onChange,
  length = 6,
  focusOnMount = true,
  disabled = false,
  onComplete,
}: OtpInputProps) {
  const refs = useRef<(HTMLInputElement | null)[]>([])

  // 挂载时聚焦首格（用 ref 编程聚焦，替代 autoFocus 属性以规避 a11y lint）
  useEffect(() => {
    if (focusOnMount) refs.current[0]?.focus()
  }, [focusOnMount])

  const emit = (next: string) => {
    const clean = next.replace(/\D/g, '').slice(0, length)
    onChange(clean)
    if (clean.length === length) onComplete?.(clean)
  }

  const focusAt = (i: number) => {
    const idx = Math.max(0, Math.min(length - 1, i))
    refs.current[idx]?.focus()
    refs.current[idx]?.select()
  }

  const handleChange = (i: number, raw: string) => {
    const digit = raw.replace(/\D/g, '')
    if (!digit) return
    // 取最后一个字符（兼容覆盖输入），写入当前格
    const chars = value.split('')
    chars[i] = digit[digit.length - 1]
    const next = chars.join('').slice(0, length)
    emit(next)
    focusAt(i + 1)
  }

  const handleKeyDown = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      e.preventDefault()
      const chars = value.split('')
      if (chars[i]) {
        chars[i] = ''
        emit(chars.join(''))
      } else {
        focusAt(i - 1)
        const prev = value.split('')
        prev[i - 1] = ''
        emit(prev.join(''))
      }
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      focusAt(i - 1)
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      focusAt(i + 1)
    }
  }

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault()
    const text = e.clipboardData.getData('text')
    emit(text)
    const filled = text.replace(/\D/g, '').slice(0, length).length
    focusAt(filled >= length ? length - 1 : filled)
  }

  return (
    <div className="flex justify-between gap-2">
      {Array.from({ length }).map((_, i) => (
        <input
          // 位置固定，用索引作 key 无副作用
          key={i}
          ref={(el) => (refs.current[i] = el)}
          type="text"
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={1}
          disabled={disabled}
          value={value[i] ?? ''}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
          className={cn(
            'border-input bg-background h-12 w-full min-w-0 rounded-lg border text-center text-lg font-semibold',
            'focus-visible:border-ring focus-visible:ring-ring/30 outline-none focus-visible:ring-2',
            'transition-colors disabled:opacity-50',
          )}
        />
      ))}
    </div>
  )
}
