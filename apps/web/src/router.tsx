import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { AuroraBackground } from '@/components/AuroraBackground'

// 路由级代码分割：每个页面单独打包，按需加载，减小首屏体积
const HomePage = lazy(() => import('@/pages/HomePage'))
const ProcessPage = lazy(() => import('@/pages/ProcessPage'))
const SimulationPage = lazy(() => import('@/pages/SimulationPage'))
const SimulationRunPage = lazy(() => import('@/pages/SimulationRunPage'))
const ReportPage = lazy(() => import('@/pages/ReportPage'))
const InteractionPage = lazy(() => import('@/pages/InteractionPage'))

/** 路由懒加载时的全屏加载占位。 */
function PageLoader() {
  return (
    <div className="flex h-screen items-center justify-center">
      <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
    </div>
  )
}

/** 全站统一外壳：玻璃流动背景铺底 + 懒加载占位。所有页面共享同一视觉地基。 */
function withSuspense(node: ReactNode) {
  return (
    <>
      <AuroraBackground />
      <Suspense fallback={<PageLoader />}>{node}</Suspense>
    </>
  )
}

export const router = createBrowserRouter([
  { path: '/', element: withSuspense(<HomePage />) },
  { path: '/process/:projectId', element: withSuspense(<ProcessPage />) },
  { path: '/simulation/:simulationId', element: withSuspense(<SimulationPage />) },
  { path: '/simulation/:simulationId/start', element: withSuspense(<SimulationRunPage />) },
  { path: '/report/:reportId', element: withSuspense(<ReportPage />) },
  { path: '/interaction/:reportId', element: withSuspense(<InteractionPage />) },
])
