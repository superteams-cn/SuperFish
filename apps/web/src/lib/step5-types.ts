/** 深度交互（Step5）相关数据类型 */

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export interface SurveyResult {
  agent_id: number
  agent_name: string
  profession?: string
  question: string
  answer: string
}
