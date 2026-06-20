import { useNavigate } from 'react-router-dom'

import { cn } from '@/lib/utils'
import { Logo } from '@/components/common/Logo'

/** 品牌标识，点击回首页。 */
export function Brand({ className }: { className?: string }) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate('/')}
      aria-label="SuperFish"
      className={cn('flex items-center', className)}
    >
      <Logo className="h-8 w-auto" />
    </button>
  )
}
