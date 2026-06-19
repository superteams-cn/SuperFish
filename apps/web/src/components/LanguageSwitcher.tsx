import { useTranslation } from 'react-i18next'
import { Languages } from 'lucide-react'

import { availableLocales } from '@/i18n'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/** 语言切换器：从 i18n 注册表读取可用语言，切换后持久化到 localStorage。 */
export function LanguageSwitcher() {
  const { i18n } = useTranslation()

  const change = (key: string) => {
    i18n.changeLanguage(key)
    localStorage.setItem('locale', key)
  }

  const current = availableLocales.find((l) => l.key === i18n.language)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Languages className="h-4 w-4" />
          {current?.label ?? i18n.language}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {availableLocales.map((locale) => (
          <DropdownMenuItem key={locale.key} onClick={() => change(locale.key)}>
            {locale.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
