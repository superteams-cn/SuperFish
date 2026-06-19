import { createBrowserRouter } from 'react-router-dom'

import HomePage from '@/pages/HomePage'
import ProcessPage from '@/pages/ProcessPage'
import SimulationPage from '@/pages/SimulationPage'
import SimulationRunPage from '@/pages/SimulationRunPage'
import ReportPage from '@/pages/ReportPage'
import InteractionPage from '@/pages/InteractionPage'

export const router = createBrowserRouter([
  { path: '/', element: <HomePage /> },
  { path: '/process/:projectId', element: <ProcessPage /> },
  { path: '/simulation/:simulationId', element: <SimulationPage /> },
  { path: '/simulation/:simulationId/start', element: <SimulationRunPage /> },
  { path: '/report/:reportId', element: <ReportPage /> },
  { path: '/interaction/:reportId', element: <InteractionPage /> },
])
