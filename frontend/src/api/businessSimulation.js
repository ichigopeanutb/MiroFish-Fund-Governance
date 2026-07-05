import service, { requestWithRetry } from './index'

export const getBusinessDemo = () => {
  return service.get('/api/business-simulation/demo')
}

export const getBusinessAccessStatus = () => {
  return service.get('/api/business-simulation/access/status')
}

export const verifyBusinessAccessCode = (code, requiredScope = 'demo') => {
  return service.post('/api/business-simulation/access/verify', {
    code,
    required_scope: requiredScope
  })
}

export const listBusinessAccessCodes = () => {
  return service.get('/api/business-simulation/access/admin/codes')
}

export const createBusinessAccessCode = (data) => {
  return service.post('/api/business-simulation/access/admin/codes', data)
}

export const updateBusinessAccessCode = (codeId, data) => {
  return service.patch(`/api/business-simulation/access/admin/codes/${codeId}`, data)
}

export const getBusinessAccessAudit = (limit = 50) => {
  return service.get('/api/business-simulation/access/admin/audit', { params: { limit } })
}

export const getBusinessSimulationHistory = (limit = 20) => {
  return service.get('/api/business-simulation/history', { params: { limit } })
}

export const createBusinessSimulation = (data) => {
  return requestWithRetry(
    () => service.post('/api/business-simulation/create', data),
    3,
    1000
  )
}

export const runBusinessSimulation = (simulationId = 'demo_business') => {
  return requestWithRetry(
    () => service.post('/api/business-simulation/run', { simulation_id: simulationId }),
    3,
    1000
  )
}

export const getBusinessSimulationStatus = (simulationId) => {
  return service.get(`/api/business-simulation/${simulationId}/status`)
}

export const getBusinessReportContext = (simulationId) => {
  return service.get(`/api/business-simulation/${simulationId}/report-context`)
}

export const getBusinessScenarioRevisions = (simulationId) => {
  return service.get(`/api/business-simulation/${simulationId}/scenario-revisions`)
}

export const generateBusinessReport = (simulationId) => {
  return service.post(`/api/business-simulation/${simulationId}/report`)
}

export const generateBusinessGovernancePacket = (simulationId) => {
  return service.post(`/api/business-simulation/${simulationId}/governance-packet`)
}

export const generateBusinessMeetingPack = (simulationId) => {
  return service.post(`/api/business-simulation/${simulationId}/meeting-pack`)
}

export const generateBusinessGovernanceRemediationPlan = (simulationId) => {
  return service.post(`/api/business-simulation/${simulationId}/governance-remediation-plan`)
}

export const getBusinessGovernanceRemediationPlan = (simulationId) => {
  return service.get(`/api/business-simulation/${simulationId}/governance-remediation-plan`)
}

export const previewBusinessGovernanceRemediationOption = (simulationId, optionId) => {
  return service.post(`/api/business-simulation/${simulationId}/governance-remediation-plan/options/${optionId}/preview`)
}

export const commitBusinessGovernanceRemediationOption = (simulationId, optionId) => {
  return requestWithRetry(
    () => service.post(`/api/business-simulation/${simulationId}/governance-remediation-plan/options/${optionId}/commit`),
    3,
    1000
  )
}

export const getBusinessGovernanceReview = (simulationId) => {
  return service.get(`/api/business-simulation/${simulationId}/governance-review`)
}

export const updateBusinessGovernanceReview = (simulationId, data) => {
  return service.post(`/api/business-simulation/${simulationId}/governance-review`, data)
}

export const commitBusinessFinancialPlan = (simulationId) => {
  return requestWithRetry(
    () => service.post(`/api/business-simulation/${simulationId}/financial-plan/commit`),
    3,
    1000
  )
}

export const commitBusinessFundTerms = (simulationId) => {
  return requestWithRetry(
    () => service.post(`/api/business-simulation/${simulationId}/fund-terms/commit`),
    3,
    1000
  )
}

export const previewBusinessScenarioPatch = (simulationId, data) => {
  return service.post(`/api/business-simulation/${simulationId}/scenario-patch/preview`, data)
}

export const commitBusinessScenarioPatch = (simulationId, data) => {
  return requestWithRetry(
    () => service.post(`/api/business-simulation/${simulationId}/scenario-patch/commit`, data),
    3,
    1000
  )
}

export const getBusinessOutput = (simulationId, filename) => {
  return service.get(`/api/business-simulation/${simulationId}/outputs/${filename}`)
}
