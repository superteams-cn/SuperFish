import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Logo } from '@/components/common/Logo'
import { resetPassword } from '@/lib/api/auth'
import { useAuth } from '@/stores/auth'

/** 重置密码落地页：邮件链接 /reset-password?token=... 跳转至此设置新密码。 */
export default function ResetPasswordPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { openAuth } = useAuth()
  const [params] = useSearchParams()
  const token = params.get('token') || ''

  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setSubmitting(true)
    try {
      const res = await resetPassword(token, password)
      if (!res.success) throw new Error(res.error || t('auth.genericError'))
      toast.success(t('auth.resetSuccess'))
      navigate('/', { replace: true })
      openAuth('login')
    } catch (err) {
      const resp = (err as { response?: { data?: { error?: string } } })?.response
      toast.error(resp?.data?.error || (err as Error)?.message || t('auth.genericError'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-5">
      <Card variant="glass" className="w-full max-w-sm p-7 shadow-xl">
        <div className="mb-6 flex flex-col items-center text-center">
          <Logo className="mb-4 h-10 w-auto" />
          <h1 className="text-xl font-semibold">{t('auth.resetPageTitle')}</h1>
          <p className="text-muted-foreground mt-1 text-sm">{t('auth.resetPageSubtitle')}</p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="reset-password">{t('auth.newPasswordLabel')}</Label>
            <Input
              id="reset-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('auth.passwordPlaceholder')}
            />
          </div>
          <Button type="submit" className="w-full gap-2" disabled={submitting || !token}>
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {submitting ? t('auth.submitting') : t('auth.submitReset')}
          </Button>
        </form>

        <button
          type="button"
          onClick={() => navigate('/')}
          className="text-muted-foreground hover:text-foreground mx-auto mt-4 block text-sm transition-colors"
        >
          {t('auth.backToSignIn')}
        </button>
      </Card>
    </div>
  )
}
