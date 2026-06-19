import { useState } from 'react'
import { Moon, Sun } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { getTheme, setTheme, type Theme } from '@/stores/theme'

/** 明暗主题切换按钮（shadcn 约定：切换 <html> 的 dark 类）。 */
export function ThemeSwitcher() {
  const [theme, setThemeState] = useState<Theme>(getTheme())

  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setThemeState(next)
  }

  return (
    <Button variant="ghost" size="icon" onClick={toggle} title="切换明暗主题">
      {theme === 'dark' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
    </Button>
  )
}
