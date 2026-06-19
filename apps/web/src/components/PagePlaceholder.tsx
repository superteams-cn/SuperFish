import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface PagePlaceholderProps {
  title: string
  /** 路由参数等调试信息 */
  detail?: string
}

/**
 * 迁移期占位页：Vue→React 重写过程中，尚未移植的路由先用此组件占位，
 * 保证路由、i18n、样式链路可端到端验证。移植完成后逐个替换。
 */
export function PagePlaceholder({ title, detail }: PagePlaceholderProps) {
  return (
    <div className="container flex min-h-screen flex-col items-center justify-center gap-6 py-12">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>该页面正在从 Vue 迁移到 React，敬请期待。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {detail && <p className="text-sm text-muted-foreground">{detail}</p>}
          <Button asChild variant="outline">
            <Link to="/">
              <ArrowLeft className="h-4 w-4" />
              返回首页
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
