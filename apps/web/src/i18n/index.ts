import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import languages from '@locales/languages.json'

// 动态加载除 languages.json 外的所有语言文件（zh.json、en.json...）
const localeFiles = import.meta.glob('../../../../packages/shared/locales/!(languages).json', {
  eager: true,
}) as Record<string, { default: Record<string, unknown> }>

const resources: Record<string, { translation: Record<string, unknown> }> = {}
export const availableLocales: { key: string; label: string }[] = []

const languageRegistry = languages as Record<string, { label: string; llmInstruction?: string }>

for (const path in localeFiles) {
  const match = path.match(/\/([^/]+)\.json$/)
  if (!match) continue
  const key = match[1]
  if (languageRegistry[key]) {
    resources[key] = { translation: localeFiles[path].default }
    availableLocales.push({ key, label: languageRegistry[key].label })
  }
}

const savedLocale = localStorage.getItem('locale') || 'zh'

i18n.use(initReactI18next).init({
  resources,
  lng: savedLocale,
  fallbackLng: 'zh',
  interpolation: { escapeValue: false },
})

export default i18n
