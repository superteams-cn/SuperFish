/** 剧本推演（kind=narrative）的前端类型，对齐后端 beats.jsonl / run-status。 */

export type BeatType = 'SPEAK' | 'ASIDE' | 'ACT' | 'MOVE' | 'DIRECT'

/** 一个 beat：后端 Beat.to_dict() + runner 解析的角色名。 */
export interface BeatItem {
  seq: number
  type: BeatType
  actor: string
  actor_name?: string
  scene_id?: string
  to?: string[]
  to_names?: string[]
  content?: string
  subtext?: string
  meta?: Record<string, unknown>
  _uniqueId?: string
}

/** 叙事 run-status（NarrativeRunner.get_run_status 的返回）。 */
export interface NarrativeRunStatus {
  kind?: 'narrative'
  simulation_id?: string
  runner_status?: 'idle' | 'running' | 'completed' | 'failed' | 'interrupted'
  beats_count?: number
  max_beats?: number
  progress_percent?: number
  error?: string
  all_beats?: BeatItem[]
  /** 若本推演是某次推演的分支 */
  branch?: { parent_id: string; from_seq: number; injection: string } | null
}
