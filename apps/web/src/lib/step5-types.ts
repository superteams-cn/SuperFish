/** 深度交互（Step5）相关数据类型 */

/** Report Agent 在生成回复时调用的单个工具记录 */
export interface ToolCall {
  tool_name?: string
  name?: string
  parameters?: Record<string, unknown>
  [k: string]: unknown
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  /** 仅 assistant 消息可能携带：本轮回复触发的工具调用日志 */
  toolCalls?: ToolCall[]
}

export interface SurveyResult {
  agent_id: number
  agent_name: string
  profession?: string
  question: string
  answer: string
}
