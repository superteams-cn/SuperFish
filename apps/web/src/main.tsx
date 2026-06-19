import React from 'react'
import ReactDOM from 'react-dom/client'

import App from '@/App'
import { initTheme } from '@/stores/theme'
import '@/i18n'
import '@/index.css'

// 挂载前应用已保存的主题，避免首屏闪烁
initTheme()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
