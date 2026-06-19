import { useNavigate } from 'react-router-dom'

import { cn } from '@/lib/utils'

/** 品牌标识，点击回首页。 */
export function Brand({ className }: { className?: string }) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate('/')}
      className={cn('font-mono text-lg font-extrabold tracking-wide', className)}
    >
      SUPERFISH
    </button>
  )
}
