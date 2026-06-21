import { useTranslation } from 'react-i18next'
import { Sparkles, User, Users, ArrowLeft, Loader2 } from 'lucide-react'

import { ChatPanel } from '@/components/step5/ChatPanel'
import { SurveyPanel } from '@/components/step5/SurveyPanel'
import { useInteraction } from '@/components/step5/useInteraction'
import { ReportOutlinePanel } from '@/components/step4/ReportOutlinePanel'
import { TextButton } from '@/components/ui/text-button'
import { SelectableCard } from '@/components/ui/selectable-card'
import { Logo } from '@/components/common/Logo'
import { cn } from '@/lib/utils'
import type { Profile } from '@/lib/step2-types'

interface Step5Props {
  reportId: string
  simulationId: string
  addLog: (msg: string) => void
}

const initial = (name?: string) => (name || 'A').charAt(0).toUpperCase()

/** 步骤五：深入追问（左：结论报告 / 右：问 SuperFish · 问一个人 · 问一群人）。 */
export function Step5Interaction({ reportId, simulationId, addLog }: Step5Props) {
  const { t } = useTranslation()

  // 全部交互逻辑（加载/唤醒/采访/问卷/切换）收拢在容器 hook 内；本组件仅做展示。
  const {
    outline,
    generatedSections,
    tab,
    profiles,
    wakingEnv,
    currentMessages,
    isSending,
    selectedAgentIndex,
    selectedAgent,
    sendMessage,
    selected,
    question,
    setQuestion,
    isSurveying,
    surveyResults,
    submitSurvey,
    toggleAgent,
    selectAllAgents,
    clearSelected,
    selectSuper,
    selectOne,
    selectCrowd,
    pickAgent,
    backToPicker,
  } = useInteraction({ reportId, simulationId, addLog })

  return (
    <div className="flex h-full overflow-hidden">
      {/* 左侧：结论报告（不透明「纸」，可对照追问；长滚动不卡） */}
      <div className="bg-background w-[44%] min-w-[400px] max-w-[660px] flex-shrink-0 overflow-y-auto border-r px-8 py-6 xl:px-10">
        <ReportOutlinePanel
          outline={outline}
          generatedSections={generatedSections}
          currentSectionIndex={null}
        />
      </div>

      {/* 右侧：追问区（透出玻璃氛围，不用白底） */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶部：身份 + 三入口 */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
          <div className="flex items-center gap-2.5">
            <Logo variant="mark" className="h-7 w-7 shrink-0 rounded-full" />
            <div className="min-w-0">
              <div className="text-sm font-semibold">{t('step5.cTitle')}</div>
              <div className="text-muted-foreground text-xs">{t('step5.cSubtitle')}</div>
            </div>
          </div>

          <div className="bg-muted/50 flex items-center gap-1 rounded-full border p-1">
            <SegBtn active={tab === 'super'} onClick={selectSuper} icon={Sparkles}>
              {t('step5.cAskSuper')}
            </SegBtn>
            {profiles.length > 0 && (
              <>
                <SegBtn active={tab === 'one'} onClick={selectOne} icon={User}>
                  {t('step5.cAskOne')}
                </SegBtn>
                <SegBtn active={tab === 'crowd'} onClick={selectCrowd} icon={Users}>
                  {t('step5.cAskCrowd')}
                </SegBtn>
              </>
            )}
          </div>
        </div>

        {/* 内容区 */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {wakingEnv && (
            <div className="flex items-center justify-center gap-2 border-b bg-indigo-500/10 px-4 py-2 text-xs text-indigo-600 dark:text-indigo-300">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {t('step5.cWaking')}
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-hidden">
            {tab === 'crowd' ? (
              <SurveyPanel
                profiles={profiles}
                selected={selected}
                onToggle={toggleAgent}
                onSelectAll={selectAllAgents}
                onClear={clearSelected}
                question={question}
                setQuestion={setQuestion}
                isSurveying={isSurveying}
                results={surveyResults}
                onSubmit={submitSurvey}
              />
            ) : tab === 'one' && selectedAgentIndex === null ? (
              <PeoplePicker profiles={profiles} onPick={pickAgent} />
            ) : tab === 'one' ? (
              <div className="flex h-full flex-col">
                <TextButton
                  onClick={backToPicker}
                  className="flex items-center gap-1.5 border-b px-4 py-2 text-xs"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  {t('step5.cChangePerson')}
                </TextButton>
                <div className="min-h-0 flex-1">
                  <ChatPanel
                    target="agent"
                    agent={selectedAgent}
                    messages={currentMessages}
                    isSending={isSending}
                    onSend={sendMessage}
                  />
                </div>
              </div>
            ) : (
              <ChatPanel
                target="report_agent"
                agent={null}
                messages={currentMessages}
                isSending={isSending}
                onSend={sendMessage}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/** 顶部三入口分段按钮 */
function SegBtn({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active?: boolean
  onClick: () => void
  icon: typeof Sparkles
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition',
        active
          ? 'bg-brand-gradient text-white shadow-sm'
          : 'text-muted-foreground hover:text-foreground',
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </button>
  )
}

/** 选人墙：挑一个推演里的人来追问 */
function PeoplePicker({
  profiles,
  onPick,
}: {
  profiles: Profile[]
  onPick: (idx: number) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="h-full overflow-y-auto px-5 py-6">
      <p className="text-muted-foreground mb-4 text-center text-sm">{t('step5.cPickPrompt')}</p>
      <div className="mx-auto grid max-w-2xl gap-3 sm:grid-cols-2">
        {profiles.map((p, idx) => (
          <SelectableCard
            key={p.username || idx}
            onClick={() => onPick(idx)}
            className="flex items-start gap-3 rounded-2xl p-4"
          >
            <div className="bg-brand-gradient flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white">
              {initial(p.name || p.username)}
            </div>
            <div className="min-w-0">
              <div className="truncate font-medium">{p.name || p.username}</div>
              <div className="text-muted-foreground truncate text-xs">
                {p.profession || t('step2.unknownProfession')}
              </div>
              {p.bio && (
                <p className="text-muted-foreground mt-1 line-clamp-2 text-xs leading-relaxed">
                  {p.bio}
                </p>
              )}
            </div>
          </SelectableCard>
        ))}
      </div>
    </div>
  )
}
