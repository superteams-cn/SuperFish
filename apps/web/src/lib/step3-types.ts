/** 模拟运行（Step3）相关数据类型 */

/** 运行状态（/run-status 返回） */
export interface RunStatus {
  twitter_running?: boolean
  twitter_completed?: boolean
  twitter_current_round?: number
  twitter_actions_count?: number
  twitter_simulated_hours?: number
  reddit_running?: boolean
  reddit_completed?: boolean
  reddit_current_round?: number
  reddit_actions_count?: number
  reddit_simulated_hours?: number
  total_rounds?: number
  runner_status?: string
  process_pid?: number
  force_restarted?: boolean
  error?: string
  [key: string]: unknown
}

/** 单条 Agent 动作 */
export interface ActionItem {
  id?: string
  _uniqueId?: string
  timestamp?: string
  platform?: 'twitter' | 'reddit' | string
  agent_id?: number
  agent_name?: string
  action_type?: string
  round_num?: number
  action_args?: {
    content?: string
    quote_content?: string
    original_content?: string
    original_author_name?: string
    post_author_name?: string
    post_content?: string
    post_id?: string | number
    query?: string
    target_user?: string
    user_id?: string | number
    [key: string]: unknown
  }
  [key: string]: unknown
}
