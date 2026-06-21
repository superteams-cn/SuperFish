import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, Loader2, XCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Logo } from '@/components/common/Logo'
import { verifyEmail } from '@/lib/api/auth'
import { useAuth } from '@/stores/auth'

type Phase = 'verifying' | 'success' | 'failed'

/** 邮箱验证落地页：邮件链接 /verify-email?token=... 跳转至此自动校验。 */
export default function VerifyEmailPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { refreshUser } = useAuth()
  const [params] = useSearchParams()
  const token = params.get('token') || ''

  const [phase, setPhase] = useState<Phase>('verifying')
  const done = useRef(false)

  useEffect(() => {
    if (done.current) return
    done.current = true
    void (async () => {
      if (!token) {
        setPhase('failed')
        return
      }
      try {
        const res = await verifyEmail(token)
        if (!res.success) throw new Error(res.error || '')
        setPhase('success')
        // 已登录则刷新本地用户态，让软门禁随即放行
        try {
          await refreshUser()
        } catch {
          /* 未登录时 /me 401，忽略 */
        }
      } catch {
        setPhase('failed')
      }
    })()
  }, [token, refreshUser])

  return (
    <div className="flex min-h-screen items-center justify-center px-5">
      <div className="glass w-full max-w-sm rounded-2xl border p-7 text-center shadow-xl backdrop-blur-xl">
        <Logo className="mx-auto mb-4 h-10 w-auto" />
        <h1 className="text-xl font-semibold">{t('auth.verifyPageTitle')}</h1>

        <div className="my-7 flex flex-col items-center gap-3">
          {phase === 'verifying' && (
            <>
              <Loader2 className="text-primary h-9 w-9 animate-spin" />
              <p className="text-muted-foreground text-sm">{t('auth.verifyPageVerifying')}</p>
            </>
          )}
          {phase === 'success' && (
            <>
              <CheckCircle2 className="h-9 w-9 text-emerald-500" />
              <p className="text-sm">{t('auth.verifyPageSuccess')}</p>
            </>
          )}
          {phase === 'failed' && (
            <>
              <XCircle className="text-destructive h-9 w-9" />
              <p className="text-muted-foreground text-sm">{t('auth.verifyPageFailed')}</p>
            </>
          )}
        </div>

        {phase !== 'verifying' && (
          <Button className="w-full" onClick={() => navigate('/', { replace: true })}>
            {t('auth.backToSignIn')}
          </Button>
        )}
      </div>
    </div>
  )
}
