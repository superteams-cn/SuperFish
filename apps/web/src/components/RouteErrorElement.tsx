import { useRouteError, isRouteErrorResponse } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { AuroraBackground } from '@/components/AuroraBackground'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

/**
 * 路由级错误兜底页：替换 React Router 默认的白底报错页，套用玻璃质感主题。
 * 捕获路由渲染/数据/懒加载（含 chunk 加载失败）异常。
 */
export function RouteErrorElement() {
  const { t } = useTranslation()
  const error = useRouteError()

  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : String(error ?? '')

  return (
    <>
      <AuroraBackground />
      <div className="flex min-h-screen flex-col items-center justify-center p-6">
        <Card
          variant="glass"
          className="flex w-full max-w-md flex-col items-center gap-5 px-8 py-10 text-center"
        >
          <div className="bg-brand-gradient flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-lg">
            <AlertTriangle className="h-7 w-7" />
          </div>
          <div className="space-y-2">
            <h1 className="text-xl font-bold tracking-tight">{t('errorBoundary.title')}</h1>
            {message && (
              <p className="text-muted-foreground max-w-sm break-words text-sm">{message}</p>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => window.location.reload()}>
              {t('errorBoundary.retry')}
            </Button>
            <Button onClick={() => (window.location.href = '/')}>
              {t('errorBoundary.backHome')}
            </Button>
          </div>
        </Card>
      </div>
    </>
  )
}
