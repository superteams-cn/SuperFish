/** 环境搭建（Step2）相关数据类型 */

/** Agent 人设 */
export interface Profile {
  name?: string
  username?: string
  profession?: string
  bio?: string
  interested_topics?: string[]
  entity_type?: string
  age?: number
  gender?: string
  country?: string
  mbti?: string
  persona?: string
  [key: string]: unknown
}

/** 时间配置 */
export interface TimeConfig {
  total_simulation_hours?: number
  minutes_per_round?: number
  agents_per_hour_min?: number
  agents_per_hour_max?: number
  peak_hours?: number[]
  peak_activity_multiplier?: number
  work_hours?: number[]
  work_activity_multiplier?: number
  morning_hours?: number[]
  morning_activity_multiplier?: number
  off_peak_hours?: number[]
  off_peak_activity_multiplier?: number
}

/** 单个 Agent 配置 */
export interface AgentConfig {
  agent_id: number
  entity_name?: string
  entity_type?: string
  stance?: string
  active_hours?: number[]
  posts_per_hour?: number
  comments_per_hour?: number
  response_delay_min?: number
  response_delay_max?: number
  activity_level?: number
  sentiment_bias?: number
  influence_weight?: number
}

/** 平台推荐算法配置 */
export interface PlatformConfig {
  recency_weight?: number
  popularity_weight?: number
  relevance_weight?: number
  viral_threshold?: number
  echo_chamber_strength?: number
}

/** 初始帖子 */
export interface InitialPost {
  poster_type?: string
  poster_agent_id: number
  content?: string
}

/** 事件配置 */
export interface EventConfig {
  narrative_direction?: string
  hot_topics?: string[]
  initial_posts: InitialPost[]
}

/** 完整模拟配置 */
export interface SimulationConfig {
  time_config?: TimeConfig
  agent_configs?: AgentConfig[]
  twitter_config?: PlatformConfig
  reddit_config?: PlatformConfig
  event_config?: EventConfig
  generation_reasoning?: string
}
