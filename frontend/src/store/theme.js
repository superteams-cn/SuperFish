import { ref } from 'vue'

const STORAGE_KEY = 'theme'

// 可用主题：浅色 / 暗色 / 包豪斯 / 多巴胺
export const THEMES = ['light', 'dark', 'bauhaus', 'dopamine']

// 全局主题状态
const theme = ref('light')

const applyTheme = (value) => {
  document.documentElement.setAttribute('data-theme', value)
}

// 在应用挂载前调用，避免首屏闪烁
export const initTheme = () => {
  const saved = localStorage.getItem(STORAGE_KEY)
  theme.value = THEMES.includes(saved) ? saved : 'light'
  applyTheme(theme.value)
}

export const setTheme = (value) => {
  if (!THEMES.includes(value)) return
  theme.value = value
  localStorage.setItem(STORAGE_KEY, value)
  applyTheme(value)
}

export const useTheme = () => ({ theme, themes: THEMES, setTheme })
