import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { InsightResult } from '@/lib/step4-types'
import {
  EntityGrid,
  FactList,
  MiniTabs,
  RelationList,
  ToolEmpty,
  ToolResultShell,
} from './tool-display-shared'

/** insight_forge（深度洞察）结构化展示：事实 / 实体 / 关系链 / 子问题。 */
export function InsightDisplay({
  result,
  resultLength,
}: {
  result: InsightResult
  resultLength?: number
}) {
  const { t } = useTranslation()
  const [tab, setTab] = useState('facts')

  const tabs = [
    { key: 'facts', label: t('step4.tabKeyFacts', { count: result.facts.length }) },
    { key: 'entities', label: t('step4.tabCoreEntities', { count: result.entities.length }) },
    { key: 'relations', label: t('step4.tabRelationChains', { count: result.relations.length }) },
  ]
  if (result.subQueries.length > 0) {
    tabs.push({
      key: 'subqueries',
      label: t('step4.tabSubQueries', { count: result.subQueries.length }),
    })
  }

  return (
    <ToolResultShell
      title={t('step4.toolDeepInsight')}
      stats={[
        { label: t('step4.statFacts'), value: result.stats.facts || result.facts.length },
        { label: t('step4.statEntities'), value: result.stats.entities || result.entities.length },
        {
          label: t('step4.statRelations'),
          value: result.stats.relationships || result.relations.length,
        },
      ]}
      resultLength={resultLength}
      query={result.query || undefined}
    >
      {result.simulationRequirement && (
        <p className="text-muted-foreground text-[11px]">
          <span className="font-medium">{t('step4.scenarioLabel')}</span>
          {result.simulationRequirement}
        </p>
      )}
      <MiniTabs tabs={tabs} active={tab} onChange={setTab} />
      <div className="pt-1">
        {tab === 'facts' &&
          (result.facts.length > 0 ? (
            <FactList facts={result.facts} />
          ) : (
            <ToolEmpty text={t('step4.emptyKeyFacts')} />
          ))}
        {tab === 'entities' &&
          (result.entities.length > 0 ? (
            <EntityGrid entities={result.entities} />
          ) : (
            <ToolEmpty text={t('step4.emptyCoreEntities')} />
          ))}
        {tab === 'relations' &&
          (result.relations.length > 0 ? (
            <RelationList relations={result.relations} />
          ) : (
            <ToolEmpty text={t('step4.emptyRelationChains')} />
          ))}
        {tab === 'subqueries' && (
          <div className="space-y-1.5">
            {result.subQueries.map((sq, i) => (
              <div key={i} className="flex gap-2 text-[11px] leading-snug">
                <span className="text-brand shrink-0 font-mono font-semibold">Q{i + 1}</span>
                <span>{sq}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </ToolResultShell>
  )
}
