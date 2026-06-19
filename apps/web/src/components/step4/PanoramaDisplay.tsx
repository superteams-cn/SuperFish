import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { PanoramaResult } from '@/lib/step4-types'
import { EntityGrid, FactList, MiniTabs, ToolEmpty, ToolResultShell } from './tool-display-shared'

/** panorama_search（全景搜索）结构化展示：当前有效事实 / 历史事实 / 涉及实体。 */
export function PanoramaDisplay({
  result,
  resultLength,
}: {
  result: PanoramaResult
  resultLength?: number
}) {
  const { t } = useTranslation()
  const [tab, setTab] = useState('active')

  const tabs = [
    { key: 'active', label: t('step4.tabActiveFacts', { count: result.activeFacts.length }) },
    {
      key: 'historical',
      label: t('step4.tabHistoricalFacts', { count: result.historicalFacts.length }),
    },
    { key: 'entities', label: t('step4.tabEntities', { count: result.entities.length }) },
  ]

  return (
    <ToolResultShell
      title={t('step4.toolPanoramaSearch')}
      stats={[
        { label: t('step4.statNodes'), value: result.stats.nodes },
        { label: t('step4.statEdges'), value: result.stats.edges },
      ]}
      resultLength={resultLength}
      query={result.query || undefined}
    >
      <MiniTabs tabs={tabs} active={tab} onChange={setTab} />
      <div className="pt-1">
        {tab === 'active' &&
          (result.activeFacts.length > 0 ? (
            <FactList facts={result.activeFacts} />
          ) : (
            <ToolEmpty text={t('step4.emptyActiveFacts')} />
          ))}
        {tab === 'historical' &&
          (result.historicalFacts.length > 0 ? (
            <FactList facts={result.historicalFacts} />
          ) : (
            <ToolEmpty text={t('step4.emptyHistoricalFacts')} />
          ))}
        {tab === 'entities' &&
          (result.entities.length > 0 ? (
            <EntityGrid entities={result.entities} initial={8} />
          ) : (
            <ToolEmpty text={t('step4.emptyEntities')} />
          ))}
      </div>
    </ToolResultShell>
  )
}
