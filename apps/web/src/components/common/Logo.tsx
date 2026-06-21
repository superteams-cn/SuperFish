import { useState } from 'react'
import { Sparkles } from 'lucide-react'

import { cn } from '@/lib/utils'

interface LogoProps {
  /** full = 横版（图标+文字），mark = 纯图标 */
  variant?: 'full' | 'mark'
  className?: string
}

/**
 * 品牌 Logo，优雅降级：
 * - 把横版 logo 放到 public/logo.png、纯图标放到 public/logo-mark.png 即自动显示
 * - 文件缺失时回退到文字 wordmark / 渐变图标，不会破图
 */
export function Logo({ variant = 'full', className }: LogoProps) {
  const [failed, setFailed] = useState(false)

  if (failed) {
    if (variant === 'mark') {
      return (
        <div
          className={cn(
            'bg-brand-gradient flex items-center justify-center rounded-full text-white',
            className,
          )}
        >
          <Sparkles className="h-4 w-4" />
        </div>
      )
    }
    return <span className="text-lg font-semibold tracking-tight">SuperFish</span>
  }

  // logo 为透明 PNG：直接贴上，无需白底卡，自适应任意背景
  return (
    <img
      src={variant === 'mark' ? '/logo-mark.png' : '/logo.png'}
      alt="SuperFish"
      className={cn('object-contain', className)}
      onError={() => setFailed(true)}
    />
  )
}
