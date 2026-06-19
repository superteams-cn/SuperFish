import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { QuickSearchResult } from '@/lib/step4-types'
import {
  EntityGrid,
  FactList,
  MiniTabs,
  RelationList,
  ToolEmpty,
  ToolResultShell,
} from './tool-display-shared'

/** quick_search（快速搜索）结构化展示：事实 / 相关关系 / 相关节点。 */
export function QuickSearchDisplay({
  result,
  resultLength,
}: {
  result: QuickSearchResult
  resultLength?: number
}) {
  const { t } = useTranslation()
  const hasEdges = result.edges.length > 0
  const hasNodes = result.nodes.length > 0
  const showTabs = hasEdges || hasNodes
  const [tab, setTab] = useState('facts')

  const tabs = [{ key: 'facts', label: t('step4.tabFacts', { count: result.facts.length }) }]
  if (hasEdges)
    tabs.push({ key: 'edges', label: t('step4.tabEdges', { count: result.edges.length }) })
  if (hasNodes)
    tabs.push({ key: 'nodes', label: t('step4.tabNodes', { count: result.nodes.length }) })

  return (
    <ToolResultShell
      title={t('step4.toolQuickSearch')}
      stats={[{ label: t('step4.statResults'), value: result.count || result.facts.length }]}
      resultLength={resultLength}
      query={result.query || undefined}
      queryLabel={result.query ? t('step4.searchLabel') : undefined}
    >
      {showTabs && <MiniTabs tabs={tabs} active={tab} onChange={setTab} />}
      <div className="pt-1">
        {(!showTabs || tab === 'facts') &&
          (result.facts.length > 0 ? (
            <FactList facts={result.facts} />
          ) : (
            <ToolEmpty text={t('step4.emptySearchResults')} />
          ))}
        {showTabs && tab === 'edges' && hasEdges && (
          <RelationList relations={result.edges} initial={20} />
        )}
        {showTabs && tab === 'nodes' && hasNodes && <EntityGrid entities={result.nodes} />}
      </div>
    </ToolResultShell>
  )
}
