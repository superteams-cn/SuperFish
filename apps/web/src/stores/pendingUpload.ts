/**
 * 临时存储待上传的文件和需求。
 * 用于首页点击「启动引擎」后立即跳转，在 Process 页面再进行 API 调用。
 * 仅在导航时一次性读取，无需响应式，模块级单例即可。
 */

/** 推演类型：社媒舆论模拟（默认）/ 剧本剧情拆解推演。与后端 project.kind 对齐。 */
export type SimulationKind = 'social_opinion' | 'narrative'

interface PendingUploadState {
  files: File[]
  simulationRequirement: string
  kind: SimulationKind
  isPending: boolean
}

const state: PendingUploadState = {
  files: [],
  simulationRequirement: '',
  kind: 'social_opinion',
  isPending: false,
}

export function setPendingUpload(
  files: File[],
  requirement: string,
  kind: SimulationKind = 'social_opinion',
) {
  state.files = files
  state.simulationRequirement = requirement
  state.kind = kind
  state.isPending = true
}

export function getPendingUpload(): PendingUploadState {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    kind: state.kind,
    isPending: state.isPending,
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.kind = 'social_opinion'
  state.isPending = false
}
