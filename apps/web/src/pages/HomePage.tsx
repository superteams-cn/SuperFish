import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Upload, X, FileText, Cpu } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { setPendingUpload } from '@/stores/pendingUpload'

const ACCEPTED = ['pdf', 'md', 'txt']

export default function HomePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [files, setFiles] = useState<File[]>([])
  const [requirement, setRequirement] = useState('')
  const [dragOver, setDragOver] = useState(false)

  const canSubmit = requirement.trim() !== '' && files.length > 0

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const valid = Array.from(incoming).filter((f) =>
      ACCEPTED.includes(f.name.split('.').pop()?.toLowerCase() ?? ''),
    )
    setFiles((prev) => [...prev, ...valid])
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const startEngine = () => {
    if (!canSubmit) return
    // 存储待上传数据后跳转，本体生成在 Process 页面进行（projectId='new' 表示新建）
    setPendingUpload(files, requirement)
    navigate('/process/new')
  }

  return (
    <div className="container max-w-5xl py-10">
      {/* 顶部：品牌 + 语言切换 */}
      <header className="mb-10 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            SuperFish
            <span className="ml-2 align-middle text-sm font-normal text-muted-foreground">
              {t('home.version')}
            </span>
          </h1>
          <p className="text-sm text-muted-foreground">{t('home.tagline')}</p>
        </div>
        <LanguageSwitcher />
      </header>

      {/* 主标题 */}
      <section className="mb-10 text-center">
        <h2 className="text-4xl font-extrabold tracking-tight md:text-5xl">
          {t('home.heroTitle1')}
          <br />
          {t('home.heroTitle2')}
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-muted-foreground">{t('home.slogan')}</p>
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        {/* 现实种子上传 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('home.realitySeed')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                addFiles(e.dataTransfer.files)
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
                dragOver ? 'border-primary bg-accent' : 'border-input hover:bg-accent/50'
              }`}
            >
              <Upload className="h-8 w-8 text-muted-foreground" />
              <p className="font-medium">{t('home.dragToUpload')}</p>
              <p className="text-xs text-muted-foreground">{t('home.orBrowse')}</p>
              <p className="text-xs text-muted-foreground">{t('home.supportedFormats')}</p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.md,.txt"
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
            />

            {files.length > 0 && (
              <ul className="space-y-2">
                {files.map((file, index) => (
                  <li
                    key={`${file.name}-${index}`}
                    className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                  >
                    <span className="flex items-center gap-2 truncate">
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="truncate">{file.name}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* 模拟提示词 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('home.simulationPrompt')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
              placeholder={t('home.promptPlaceholder')}
              className="min-h-[180px]"
            />
            <div className="flex items-center justify-between">
              <Badge variant="secondary" className="gap-1">
                <Cpu className="h-3 w-3" />
                {t('home.engineBadge')}
              </Badge>
              <Button onClick={startEngine} disabled={!canSubmit}>
                {t('home.startEngine')}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
