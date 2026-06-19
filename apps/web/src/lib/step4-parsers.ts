/**
 * 工具结果解析器：把 ReportAgent 各工具返回的 markdown 文本解析为结构化数据，
 * 供 step4/ 下的专用展示组件渲染。解析失败时返回空骨架，由展示组件兜底为原始 JSON/文本。
 * （从旧版 Vue Step4Report.vue 的 parse* 函数移植，字段口径保持一致。）
 */
import type {
  InsightResult,
  InterviewRecord,
  InterviewResult,
  NamedEntity,
  PanoramaResult,
  QuickSearchResult,
  RelationLink,
} from './step4-types'

/** 工具结果可能是字符串，也可能被序列化成对象；统一转成字符串再解析。 */
export function toResultText(result: unknown): string {
  if (result == null) return ''
  if (typeof result === 'string') return result
  try {
    return JSON.stringify(result)
  } catch {
    return String(result)
  }
}

function parseRelation(line: string): RelationLink | null {
  const m = line.match(/^-\s*(.+?)\s*--\[(.+?)\]-->\s*(.+)$/)
  if (m) return { source: m[1].trim(), relation: m[2].trim(), target: m[3].trim() }
  return null
}

export function parseInsightForge(text: string): InsightResult {
  const result: InsightResult = {
    query: '',
    simulationRequirement: '',
    stats: { facts: 0, entities: 0, relationships: 0 },
    subQueries: [],
    facts: [],
    entities: [],
    relations: [],
  }
  try {
    const queryMatch = text.match(/分析问题:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()

    const reqMatch = text.match(/预测场景:\s*(.+?)(?:\n|$)/)
    if (reqMatch) result.simulationRequirement = reqMatch[1].trim()

    const factMatch = text.match(/相关预测事实:\s*(\d+)/)
    const entityMatch = text.match(/涉及实体:\s*(\d+)/)
    const relMatch = text.match(/关系链:\s*(\d+)/)
    if (factMatch) result.stats.facts = parseInt(factMatch[1], 10)
    if (entityMatch) result.stats.entities = parseInt(entityMatch[1], 10)
    if (relMatch) result.stats.relationships = parseInt(relMatch[1], 10)

    const subQSection = text.match(/### 分析的子问题\n([\s\S]*?)(?=\n###|$)/)
    if (subQSection) {
      result.subQueries = subQSection[1]
        .split('\n')
        .filter((l) => /^\d+\./.test(l))
        .map((l) => l.replace(/^\d+\.\s*/, '').trim())
        .filter(Boolean)
    }

    const factsSection = text.match(/### 【关键事实】[\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (factsSection) {
      result.facts = factsSection[1]
        .split('\n')
        .filter((l) => /^\d+\./.test(l))
        .map((l) => {
          const m = l.match(/^\d+\.\s*"?(.+?)"?\s*$/)
          return m ? m[1].replace(/^"|"$/g, '').trim() : l.replace(/^\d+\.\s*/, '').trim()
        })
        .filter(Boolean)
    }

    const entitySection = text.match(/### 【核心实体】\n([\s\S]*?)(?=\n###|$)/)
    if (entitySection) {
      const entityBlocks = entitySection[1]
        .split(/\n(?=- \*\*)/)
        .filter((b) => b.trim().startsWith('- **'))
      result.entities = entityBlocks
        .map((block): NamedEntity => {
          const nameMatch = block.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
          const summaryMatch = block.match(/摘要:\s*"?(.+?)"?(?:\n|$)/)
          const relatedMatch = block.match(/相关事实:\s*(\d+)/)
          return {
            name: nameMatch ? nameMatch[1].trim() : '',
            type: nameMatch ? nameMatch[2].trim() : '',
            summary: summaryMatch ? summaryMatch[1].trim() : '',
            relatedFactsCount: relatedMatch ? parseInt(relatedMatch[1], 10) : 0,
          }
        })
        .filter((e) => e.name)
    }

    const relSection = text.match(/### 【关系链】\n([\s\S]*?)(?=\n###|$)/)
    if (relSection) {
      result.relations = relSection[1]
        .split('\n')
        .filter((l) => l.trim().startsWith('-'))
        .map(parseRelation)
        .filter((r): r is RelationLink => r !== null)
    }
  } catch {
    /* 解析失败：返回已填充的部分结果 */
  }
  return result
}

export function parsePanorama(text: string): PanoramaResult {
  const result: PanoramaResult = {
    query: '',
    stats: { nodes: 0, edges: 0, activeFacts: 0, historicalFacts: 0 },
    activeFacts: [],
    historicalFacts: [],
    entities: [],
  }
  try {
    const queryMatch = text.match(/查询:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()

    const nodesMatch = text.match(/总节点数:\s*(\d+)/)
    const edgesMatch = text.match(/总边数:\s*(\d+)/)
    const activeMatch = text.match(/当前有效事实:\s*(\d+)/)
    const histMatch = text.match(/历史\/过期事实:\s*(\d+)/)
    if (nodesMatch) result.stats.nodes = parseInt(nodesMatch[1], 10)
    if (edgesMatch) result.stats.edges = parseInt(edgesMatch[1], 10)
    if (activeMatch) result.stats.activeFacts = parseInt(activeMatch[1], 10)
    if (histMatch) result.stats.historicalFacts = parseInt(histMatch[1], 10)

    const activeSection = text.match(/### 【当前有效事实】[\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (activeSection) {
      result.activeFacts = activeSection[1]
        .split('\n')
        .filter((l) => /^\d+\./.test(l))
        .map((l) =>
          l
            .replace(/^\d+\.\s*/, '')
            .replace(/^"|"$/g, '')
            .trim(),
        )
        .filter(Boolean)
    }

    const histSection = text.match(/### 【历史\/过期事实】[\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (histSection) {
      result.historicalFacts = histSection[1]
        .split('\n')
        .filter((l) => /^\d+\./.test(l))
        .map((l) =>
          l
            .replace(/^\d+\.\s*/, '')
            .replace(/^"|"$/g, '')
            .trim(),
        )
        .filter(Boolean)
    }

    const entitySection = text.match(/### 【涉及实体】\n([\s\S]*?)(?=\n###|$)/)
    if (entitySection) {
      result.entities = entitySection[1]
        .split('\n')
        .filter((l) => l.trim().startsWith('-'))
        .map((l): NamedEntity | null => {
          const m = l.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
          return m ? { name: m[1].trim(), type: m[2].trim() } : null
        })
        .filter((e): e is NamedEntity => e !== null)
    }
  } catch {
    /* noop */
  }
  return result
}

function parseIndividualReasons(reasonText: string): Record<string, string> {
  const reasons: Record<string, string> = {}
  if (!reasonText) return reasons
  const lines = reasonText.split(/\n+/)
  let currentName: string | null = null
  let currentReason: string[] = []

  for (const line of lines) {
    let name: string | null = null
    let reasonStart: string | null = null

    let headerMatch = line.match(
      /^\d+\.\s*\*\*([^*（(]+)(?:[（(]index\s*=?\s*\d+[)）])?\*\*[：:]\s*(.*)/,
    )
    if (headerMatch) {
      name = headerMatch[1].trim()
      reasonStart = headerMatch[2]
    }
    if (!headerMatch) {
      headerMatch = line.match(/^-\s*选择([^（(]+)(?:[（(]index\s*=?\s*\d+[)）])?[：:]\s*(.*)/)
      if (headerMatch) {
        name = headerMatch[1].trim()
        reasonStart = headerMatch[2]
      }
    }
    if (!headerMatch) {
      headerMatch = line.match(/^-\s*\*\*([^*（(]+)(?:[（(]index\s*=?\s*\d+[)）])?\*\*[：:]\s*(.*)/)
      if (headerMatch) {
        name = headerMatch[1].trim()
        reasonStart = headerMatch[2]
      }
    }

    if (name) {
      if (currentName && currentReason.length > 0) {
        reasons[currentName] = currentReason.join(' ').trim()
      }
      currentName = name
      currentReason = reasonStart ? [reasonStart.trim()] : []
    } else if (currentName && line.trim() && !/^未选|^综上|^最终选择/.test(line)) {
      currentReason.push(line.trim())
    }
  }
  if (currentName && currentReason.length > 0) {
    reasons[currentName] = currentReason.join(' ').trim()
  }
  return reasons
}

export function parseInterview(text: string): InterviewResult {
  const result: InterviewResult = {
    topic: '',
    successCount: 0,
    totalCount: 0,
    selectionReason: '',
    interviews: [],
    summary: '',
  }
  try {
    const topicMatch = text.match(/\*\*采访主题:\*\*\s*(.+?)(?:\n|$)/)
    if (topicMatch) result.topic = topicMatch[1].trim()

    const countMatch = text.match(/\*\*采访人数:\*\*\s*(\d+)\s*\/\s*(\d+)/)
    if (countMatch) {
      result.successCount = parseInt(countMatch[1], 10)
      result.totalCount = parseInt(countMatch[2], 10)
    }

    const reasonMatch = text.match(/### 采访对象选择理由\n([\s\S]*?)(?=\n---\n|\n### 采访实录)/)
    if (reasonMatch) result.selectionReason = reasonMatch[1].trim()

    const individualReasons = parseIndividualReasons(result.selectionReason)

    const interviewBlocks = text.split(/#### 采访 #\d+:/).slice(1)
    interviewBlocks.forEach((block, index) => {
      const interview: InterviewRecord = {
        num: index + 1,
        title: '',
        name: '',
        role: '',
        bio: '',
        selectionReason: '',
        questions: [],
        twitterAnswer: '',
        redditAnswer: '',
        quotes: [],
      }

      const titleMatch = block.match(/^(.+?)\n/)
      if (titleMatch) interview.title = titleMatch[1].trim()

      const nameRoleMatch = block.match(/\*\*(.+?)\*\*\s*\((.+?)\)/)
      if (nameRoleMatch) {
        interview.name = nameRoleMatch[1].trim()
        interview.role = nameRoleMatch[2].trim()
        interview.selectionReason = individualReasons[interview.name] || ''
      }

      const bioMatch = block.match(/_简介:\s*([\s\S]*?)_\n/)
      if (bioMatch) interview.bio = bioMatch[1].trim()

      const qMatch = block.match(/\*\*Q:\*\*\s*([\s\S]*?)(?=\n\n\*\*A:\*\*|\*\*A:\*\*)/)
      if (qMatch) {
        const qText = qMatch[1].trim()
        const questions = qText.split(/\n\d+\.\s+/).filter((q) => q.trim())
        if (questions.length > 0) {
          const firstQ = qText.match(/^1\.\s+(.+)/)
          if (firstQ) {
            interview.questions = [firstQ[1].trim(), ...questions.slice(1).map((q) => q.trim())]
          } else {
            interview.questions = questions.map((q) => q.trim())
          }
        }
      }

      const answerMatch = block.match(/\*\*A:\*\*\s*([\s\S]*?)(?=\*\*关键引言|$)/)
      if (answerMatch) {
        const answerText = answerMatch[1].trim()
        const twitterMatch = answerText.match(
          /【Twitter平台回答】\n?([\s\S]*?)(?=【Reddit平台回答】|$)/,
        )
        const redditMatch = answerText.match(/【Reddit平台回答】\n?([\s\S]*?)$/)
        if (twitterMatch) interview.twitterAnswer = twitterMatch[1].trim()
        if (redditMatch) interview.redditAnswer = redditMatch[1].trim()

        if (!twitterMatch && redditMatch) {
          if (interview.redditAnswer && interview.redditAnswer !== '（该平台未获得回复）') {
            interview.twitterAnswer = interview.redditAnswer
          }
        } else if (twitterMatch && !redditMatch) {
          if (interview.twitterAnswer && interview.twitterAnswer !== '（该平台未获得回复）') {
            interview.redditAnswer = interview.twitterAnswer
          }
        } else if (!twitterMatch && !redditMatch) {
          interview.twitterAnswer = answerText
        }
      }

      const quotesMatch = block.match(/\*\*关键引言:\*\*\n([\s\S]*?)(?=\n---|\n####|$)/)
      if (quotesMatch) {
        const quotesText = quotesMatch[1]
        let quoteMatches = quotesText.match(/> "([^"]+)"/g)
        if (!quoteMatches) {
          quoteMatches = quotesText.match(/> [“"]([^”"]+)[”"]/g)
        }
        if (quoteMatches) {
          interview.quotes = quoteMatches
            .map((q) =>
              q
                .replace(/^> [“"]|[”"]$/g, '')
                .replace(/^> "|"$/g, '')
                .trim(),
            )
            .filter(Boolean)
        }
      }

      if (interview.name || interview.title) result.interviews.push(interview)
    })

    const summaryMatch = text.match(/### 采访摘要与核心观点\n([\s\S]*?)$/)
    if (summaryMatch) result.summary = summaryMatch[1].trim()
  } catch {
    /* noop */
  }
  return result
}

export function parseQuickSearch(text: string): QuickSearchResult {
  const result: QuickSearchResult = {
    query: '',
    count: 0,
    facts: [],
    edges: [],
    nodes: [],
  }
  try {
    const queryMatch = text.match(/搜索查询:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()

    const countMatch = text.match(/找到\s*(\d+)\s*条/)
    if (countMatch) result.count = parseInt(countMatch[1], 10)

    const factsSection = text.match(/### 相关事实:\n([\s\S]*)$/)
    if (factsSection) {
      result.facts = factsSection[1]
        .split('\n')
        .filter((l) => /^\d+\./.test(l))
        .map((l) => l.replace(/^\d+\.\s*/, '').trim())
        .filter(Boolean)
    }

    const edgesSection = text.match(/### 相关边:\n([\s\S]*?)(?=\n###|$)/)
    if (edgesSection) {
      result.edges = edgesSection[1]
        .split('\n')
        .filter((l) => l.trim().startsWith('-'))
        .map(parseRelation)
        .filter((e): e is RelationLink => e !== null)
    }

    const nodesSection = text.match(/### 相关节点:\n([\s\S]*?)(?=\n###|$)/)
    if (nodesSection) {
      result.nodes = nodesSection[1]
        .split('\n')
        .filter((l) => l.trim().startsWith('-'))
        .map((l): NamedEntity | null => {
          const m = l.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
          if (m) return { name: m[1].trim(), type: m[2].trim() }
          const simple = l.match(/^-\s*(.+)$/)
          if (simple) return { name: simple[1].trim(), type: '' }
          return null
        })
        .filter((n): n is NamedEntity => n !== null)
    }
  } catch {
    /* noop */
  }
  return result
}
