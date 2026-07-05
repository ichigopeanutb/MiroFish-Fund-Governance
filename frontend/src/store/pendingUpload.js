/**
 * 临时存储待上传的文件和需求
 * 用于首页点击启动引擎后立即跳转，在Process页面再进行API调用
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  simulationRequirement: '',
  engineType: 'oasis_social',
  isPending: false
})

export function setPendingUpload(files, requirement, engineType = 'oasis_social') {
  state.files = files
  state.simulationRequirement = requirement
  state.engineType = engineType
  state.isPending = true
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    engineType: state.engineType,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.engineType = 'oasis_social'
  state.isPending = false
}

export default state
