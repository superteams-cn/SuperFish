import { useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Upload, X, FileText, ArrowUp, Sparkles, RotateCcw, History, Paperclip } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { ThemeSwitcher } from '@/components/ThemeSwitcher'
import { AuthButton } from '@/components/auth/AuthButton'
import { HistoryDatabase } from '@/components/HistoryDatabase'
import { Logo } from '@/components/common/Logo'
import { setPendingUpload } from '@/stores/pendingUpload'
import { useAuth } from '@/stores/auth'

const ACCEPTED = ['pdf', 'md', 'txt']
const THINK_MS = 750

// 主操作的品牌渐变：业务层一次性强调样式，不进组件 variant
const GRADIENT_BTN =
  'bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 text-white shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/40'

type Stage = 'topic' | 'material' | 'ready'

function AiAvatar() {
  return <Logo variant="mark" className="h-9 w-9 shrink-0 rounded-full shadow-md" />
}

/** SuperFish 气泡 */
function Bubble({ children }: { children: ReactNode }) {
  return (
    <div className="animate-rise-in flex items-start gap-3">
      <AiAvatar />
      <div className="bg-card max-w-[82%] rounded-3xl rounded-tl-lg border px-5 py-3.5 text-sm leading-relaxed shadow-lg backdrop-blur-xl sm:text-base">
        {children}
      </div>
    </div>
  )
}

/** “正在输入”指示，给对话真实的节奏感 */
function TypingBubble() {
  return (
    <div className="animate-rise-in flex items-start gap-3">
      <AiAvatar />
      <div className="bg-card flex items-center gap-1.5 rounded-3xl rounded-tl-lg border px-5 py-4 shadow-lg backdrop-blur-xl">
        <span className="bg-foreground/40 h-2 w-2 animate-bounce rounded-full [animation-delay:-0.3s]" />
        <span className="bg-foreground/40 h-2 w-2 animate-bounce rounded-full [animation-delay:-0.15s]" />
        <span className="bg-foreground/40 h-2 w-2 animate-bounce rounded-full" />
      </div>
    </div>
  )
}

/** 用户气泡 */
function UserBubble({ children }: { children: ReactNode }) {
  return (
    <div className="animate-rise-in flex justify-end">
      <div className="max-w-[82%] rounded-3xl rounded-tr-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 px-5 py-3.5 text-sm leading-relaxed text-white shadow-lg shadow-indigo-500/25 sm:text-base">
        {children}
      </div>
    </div>
  )
}

export default function HomePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { isAuthenticated, openAuth } = useAuth()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const timerRef = useRef<number>()

  const [stage, setStage] = useState<Stage>('topic')
  const [thinking, setThinking] = useState(false)
  const [draft, setDraft] = useState('')
  const [requirement, setRequirement] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [hasHistory, setHasHistory] = useState<boolean | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  // 推进到下一段对话：先让 SuperFish “想一下”，再开口，制造真实节奏
  const advanceTo = (next: Stage) => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    setStage(next)
    if (reduce) return
    setThinking(true)
    window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => setThinking(false), THINK_MS)
  }

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const valid = Array.from(incoming).filter((f) =>
      ACCEPTED.includes(f.name.split('.').pop()?.toLowerCase() ?? ''),
    )
    setFiles((prev) => [...prev, ...valid])
  }
  const removeFile = (index: number) => setFiles((prev) => prev.filter((_, i) => i !== index))

  const submitTopic = (text: string) => {
    const value = text.trim()
    if (!value) return
    // 发起预测前必须登录：未登录直接唤起登录弹框
    if (!isAuthenticated) {
      openAuth('login')
      return
    }
    setRequirement(value)
    setDraft('')
    // 已经先传了材料 → 直接就绪；否则进入“邀请上传材料”一步
    advanceTo(files.length > 0 ? 'ready' : 'material')
  }

  const restart = () => {
    window.clearTimeout(timerRef.current)
    setThinking(false)
    setStage('topic')
    setRequirement('')
    setDraft('')
    setFiles([])
  }

  const startEngine = () => {
    if (!requirement || files.length === 0) return
    setPendingUpload(files, requirement)
    navigate('/process/new')
  }

  // 已选文件清单（topic 与 material 两步共用）
  const fileList = () =>
    files.length > 0 ? (
      <ul className="flex flex-col gap-2">
        {files.map((file, index) => (
          <li
            key={`${file.name}-${index}`}
            className="bg-card animate-rise-in flex items-center justify-between rounded-xl border px-3 py-2 text-sm backdrop-blur-xl"
          >
            <span className="flex items-center gap-2 truncate">
              <FileText className="h-4 w-4 shrink-0 text-indigo-500" />
              <span className="truncate">{file.name}</span>
            </span>
            <button
              type="button"
              onClick={() => removeFile(index)}
              aria-label="移除文件"
              className="text-muted-foreground hover:text-destructive rounded-md p-0.5 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </li>
        ))}
      </ul>
    ) : null

  return (
    <div className="relative">
      {/* 极简悬浮顶栏 */}
      <header className="fixed inset-x-0 top-0 z-30 flex items-center justify-between px-5 py-4 sm:px-8">
        <Logo className="h-10 w-auto sm:h-11" />
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            className="gap-1.5 rounded-full"
            onClick={() => (isAuthenticated ? setHistoryOpen(true) : openAuth('login'))}
          >
            <History className="h-4 w-4" />
            <span className="hidden sm:inline">{t('home.records')}</span>
          </Button>
          <ThemeSwitcher />
          <LanguageSwitcher />
          <AuthButton />
        </div>
      </header>

      {/* 对话式引导 */}
      <section className="mx-auto flex min-h-screen w-full max-w-xl flex-col justify-center gap-4 px-5 py-28">
        {/* 共用的文件选择器（附件按钮与上传区都触发它） */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.md,.txt"
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />

        {/* 1. 开场 + 提问 */}
        <Bubble>
          <p className="font-medium">{t('home.chatHi')}</p>
          <p className="mt-1">{t('home.chatAskTopic')}</p>
        </Bubble>

        {stage === 'topic' ? (
          <div className="animate-rise-in ml-12 flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              {(['chatEg1', 'chatEg2', 'chatEg3'] as const).map((k) => (
                <Button
                  key={k}
                  variant="secondary"
                  size="sm"
                  className="text-muted-foreground hover:text-foreground h-auto rounded-full px-3.5 py-1.5 font-normal"
                  onClick={() => submitTopic(t(`home.${k}`))}
                >
                  {t(`home.${k}`)}
                </Button>
              ))}
            </div>

            {/* 先传的文件显示在输入框上方 */}
            {fileList()}

            <div className="bg-card flex items-end gap-1.5 rounded-3xl border p-2 shadow-lg backdrop-blur-xl">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-muted-foreground hover:text-foreground shrink-0 rounded-full"
                onClick={() => fileInputRef.current?.click()}
                aria-label={t('home.chatUploadHint')}
                title={t('home.chatUploadHint')}
              >
                <Paperclip className="h-5 w-5" />
              </Button>
              <Textarea
                rows={1}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submitTopic(draft)
                  }
                }}
                placeholder={t('home.chatInputPlaceholder')}
                className="max-h-32 min-h-[44px] flex-1 resize-none border-0 bg-transparent py-2.5 text-sm shadow-none focus-visible:ring-0 sm:text-base"
              />
              <Button
                size="icon"
                className={`${GRADIENT_BTN} size-10 shrink-0 rounded-full`}
                onClick={() => submitTopic(draft)}
                disabled={!draft.trim()}
                aria-label={t('home.chatGo')}
              >
                <ArrowUp className="h-5 w-5" />
              </Button>
            </div>
          </div>
        ) : (
          <UserBubble>{requirement}</UserBubble>
        )}

        {/* 2. 邀请上传材料（thinking 时先显示“正在输入”） */}
        {stage !== 'topic' &&
          (stage === 'material' && thinking ? (
            <TypingBubble />
          ) : (
            <>
              <Bubble>{t('home.chatAskMaterial')}</Bubble>

              {stage === 'material' ? (
                <div className="animate-rise-in ml-12 flex flex-col gap-3">
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label={t('home.chatUploadHint')}
                    onClick={() => fileInputRef.current?.click()}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        fileInputRef.current?.click()
                      }
                    }}
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
                    className={`bg-card group flex cursor-pointer items-center gap-3 rounded-2xl border border-dashed px-5 py-4 backdrop-blur-xl transition-all duration-300 ${
                      dragOver
                        ? 'scale-[1.01] border-indigo-400 bg-indigo-500/10'
                        : 'hover:bg-accent'
                    }`}
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-blue-500 text-white shadow-md transition-transform duration-300 group-hover:-translate-y-0.5">
                      <Upload className="h-5 w-5" />
                    </div>
                    <span className="text-muted-foreground text-sm">
                      {t('home.chatUploadHint')}
                    </span>
                  </div>

                  {fileList()}

                  <Button
                    size="sm"
                    className={`${GRADIENT_BTN} h-auto self-start rounded-full px-5 py-2.5`}
                    onClick={() => advanceTo('ready')}
                    disabled={files.length === 0}
                  >
                    {files.length === 0 ? t('home.chatNeedFile') : t('home.chatContinue')}
                  </Button>
                </div>
              ) : (
                <>
                  <UserBubble>{t('home.chatUserMaterial', { count: files.length })}</UserBubble>
                  {thinking ? (
                    <TypingBubble />
                  ) : (
                    <>
                      <Bubble>{t('home.chatReady')}</Bubble>
                      <div className="animate-rise-in ml-12 flex flex-wrap items-center gap-3">
                        <Button
                          className={`${GRADIENT_BTN} h-12 gap-2 rounded-full px-8 text-base`}
                          onClick={startEngine}
                        >
                          <Sparkles className="h-5 w-5" />
                          {t('home.chatGo')}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-muted-foreground gap-1.5"
                          onClick={restart}
                        >
                          <RotateCcw className="h-4 w-4" />
                          {t('home.chatRestart')}
                        </Button>
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          ))}
      </section>

      {/* 历史：从顶栏「记录」唤出的 radix Dialog 浮层 */}
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-h-[85vh] max-w-4xl overflow-y-auto">
          <DialogTitle className="sr-only">{t('home.records')}</DialogTitle>
          <HistoryDatabase onHasProjects={setHasHistory} />
          {hasHistory === false && (
            <p className="text-muted-foreground py-16 text-center text-sm">{t('home.noHistory')}</p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
