/**
 * 明暗主题：采用 shadcn/ui 约定，在 <html> 上切换 `dark` 类。
 * 放弃旧版多套自定义主题，仅保留 light / dark。
 */
const STORAGE_KEY = 'theme'
export type Theme = 'light' | 'dark'

function apply(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

/** 应用启动前调用，避免首屏闪烁。 */
export function initTheme() {
  const saved = (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? 'light'
  apply(saved)
}

export function getTheme(): Theme {
  return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? 'light'
}

export function setTheme(theme: Theme) {
  localStorage.setItem(STORAGE_KEY, theme)
  apply(theme)
}
