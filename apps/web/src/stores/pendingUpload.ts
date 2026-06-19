/**
 * 临时存储待上传的文件和需求。
 * 用于首页点击「启动引擎」后立即跳转，在 Process 页面再进行 API 调用。
 * 仅在导航时一次性读取，无需响应式，模块级单例即可。
 */

interface PendingUploadState {
  files: File[]
  simulationRequirement: string
  isPending: boolean
}

const state: PendingUploadState = {
  files: [],
  simulationRequirement: '',
  isPending: false,
}

export function setPendingUpload(files: File[], requirement: string) {
  state.files = files
  state.simulationRequirement = requirement
  state.isPending = true
}

export function getPendingUpload(): PendingUploadState {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    isPending: state.isPending,
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.isPending = false
}
