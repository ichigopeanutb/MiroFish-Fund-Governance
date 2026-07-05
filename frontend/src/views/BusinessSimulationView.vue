<template>
  <div v-if="accessChecking" class="business-view access-view">
    <section class="access-panel">
      <div class="access-brand">MIROFISH FUND GOVERNANCE EDITION</div>
      <h1>Checking Private Beta Access</h1>
      <p>Preparing the owner-controlled beta gate.</p>
    </section>
  </div>
  <div v-else-if="requiresAccess && !accessGranted" class="business-view access-view">
    <section class="access-panel">
      <div class="access-brand">MIROFISH FUND GOVERNANCE EDITION</div>
      <h1>Private Beta Access</h1>
      <p>
        Enter the access code provided by the project owner to view the fund-governance demo.
      </p>
      <form class="access-form" @submit.prevent="unlockBusinessDemo">
        <input
          v-model="accessCode"
          type="password"
          autocomplete="current-password"
          placeholder="Access code"
          autofocus
        />
        <button type="submit">Enter Demo</button>
      </form>
      <p class="access-error" v-if="accessError">{{ accessError }}</p>
      <p class="access-note" v-if="accessProfile">
        Access group: {{ accessProfile.group }} / {{ accessProfile.label }}
      </p>
      <p class="access-note">
        This gate is for invitation-only beta distribution. Do not put real fund, LP, legal, tax, or accounting data into a public demo.
      </p>
    </section>
  </div>
  <div v-else class="business-view">
    <header class="topbar">
      <button class="brand" @click="router.push('/')">MIROFISH</button>
      <div class="status-strip">
        <span class="pill">Business Governance Engine</span>
        <span class="mono">{{ currentSimulationId }}</span>
        <span class="status" :class="statusClass">{{ statusText }}</span>
      </div>
      <div class="actions">
        <button class="ghost-btn" @click="loadAll" :disabled="loading">Refresh</button>
        <button class="primary-btn" @click="runDemo" :disabled="loading">
          {{ loading ? 'Running...' : 'Run Fund Simulation' }}
        </button>
        <button class="ghost-btn" @click="buildReport" :disabled="loading || !reportContext">Generate Report</button>
        <button class="ghost-btn" @click="buildGovernancePacket" :disabled="loading || !reportContext">Generate Packet</button>
        <button class="ghost-btn" @click="buildMeetingPack" :disabled="loading || !reportContext">Generate Meeting Pack</button>
        <button class="ghost-btn" @click="buildRemediationPlan" :disabled="loading || !packetStatus">Generate Remediation</button>
      </div>
    </header>

    <main class="workspace">
      <section class="summary-band">
        <div class="metric">
          <span class="label">Events</span>
          <span class="value">{{ timeline.length }}</span>
        </div>
        <div class="metric">
          <span class="label">Capital Called</span>
          <span class="value">{{ money(cashflow.capital_called) }}</span>
        </div>
        <div class="metric">
          <span class="label">Capital Paid</span>
          <span class="value">{{ money(cashflow.capital_paid) }}</span>
        </div>
        <div class="metric">
          <span class="label">Unfunded</span>
          <span class="value">{{ money(cashflow.unfunded_commitment) }}</span>
        </div>
        <div class="metric">
          <span class="label">NAV</span>
          <span class="value">{{ money(cashflow.net_asset_value) }}</span>
        </div>
        <div class="metric">
          <span class="label">Distributions</span>
          <span class="value">{{ money(cashflow.distributions) }}</span>
        </div>
        <div class="metric">
          <span class="label">Ledger</span>
          <span class="value">{{ ledgerBalanced }}</span>
        </div>
        <div class="metric">
          <span class="label">Audit</span>
          <span class="value">{{ auditStatus }}</span>
        </div>
      </section>

      <section class="content-grid">
        <div class="main-column">
          <section class="panel">
            <div class="panel-header">
              <h2>Fund Operation Timeline</h2>
              <span class="subtle">{{ timeline.length }} object-centric events</span>
            </div>
            <div class="timeline">
              <div v-for="item in timeline" :key="`${item.simulation_time}-${item.event_type}`" class="timeline-row">
                <div class="date mono">{{ item.simulation_time }}</div>
                <div class="event-body">
                  <div class="event-title">{{ item.event_type }}</div>
                  <p>{{ item.summary }}</p>
                  <div class="object-list">
                    <span v-for="ref in item.object_refs" :key="ref" class="object-chip" :title="ref">{{ objectLabel(ref) }}</span>
                  </div>
                </div>
              </div>
              <div v-if="timeline.length === 0" class="empty">No timeline yet. Run the fund simulation.</div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Generated Business Report</h2>
              <span class="subtle">{{ reportBytes ? `${reportBytes} bytes` : 'not generated' }}</span>
            </div>
            <pre class="report-preview">{{ reportMarkdown || 'Generate a report to preview the markdown output.' }}</pre>
          </section>
        </div>

        <aside class="side-column">
          <section class="panel">
            <div class="panel-header">
              <h2>LP Capital Lifecycle</h2>
              <span class="subtle">{{ lpReadiness.status || 'not reviewed' }}</span>
            </div>
            <div class="plan-box">
              <div class="source-row">
                <span>Call rounds</span>
                <b>{{ lifecycle.capital_call_rounds || 0 }}</b>
              </div>
              <div class="source-row">
                <span>Unfunded</span>
                <b>{{ money(lifecycle.commitment_summary?.unfunded_commitment) }}</b>
              </div>
              <div class="source-row">
                <span>Paid-in multiple</span>
                <b>{{ multiple(lifecycle.nav_summary?.paid_in_multiple) }}</b>
              </div>
              <div class="source-row">
                <span>Follow-on gap</span>
                <b>{{ money(lifecycle.follow_on_reserve?.gap) }}</b>
              </div>
              <div class="capital-call-row" v-for="call in capitalCallSchedule" :key="call.call_id">
                <div>
                  <span class="mono">Round {{ call.round }}</span>
                  <b>{{ money(call.amount) }}</b>
                  <small>{{ call.purpose }} / {{ call.status }}</small>
                </div>
                <em>{{ call.due_date }}</em>
              </div>
              <div v-if="capitalCallSchedule.length === 0" class="empty compact">No capital call schedule found.</div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>LP Readiness</h2>
              <span class="subtle">strategy / resources</span>
            </div>
            <div class="plan-box">
              <div v-for="item in lpReadinessItems" :key="item.item" class="readiness-row">
                <div>
                  <b>{{ item.item }}</b>
                  <small>{{ item.owner }}</small>
                </div>
                <span class="object-chip" :class="{ warn: item.status !== 'ready' }">{{ item.status }}</span>
              </div>
              <p class="hint-note">{{ lpReadiness.recommended_next_step || 'Run the simulation to generate LP readiness.' }}</p>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>NAV Snapshots</h2>
              <span class="subtle">{{ navSnapshots.length }} periods</span>
            </div>
            <div class="plan-box">
              <div class="nav-row" v-for="item in navSnapshots" :key="`${item.simulation_time}-${item.label}`">
                <div>
                  <span class="mono">{{ item.simulation_time }}</span>
                  <b>{{ item.label }}</b>
                </div>
                <em>{{ money(item.net_asset_value) }}</em>
              </div>
              <div v-if="navSnapshots.length === 0" class="empty compact">No NAV snapshots found.</div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Evidence Bindings</h2>
              <span class="subtle">{{ evidenceBindingCount }} refs</span>
            </div>
            <div class="plan-box">
              <div class="source-row">
                <span>Policy</span>
                <b>{{ evidenceBindings.binding_policy || 'evidence_only' }}</b>
              </div>
              <div v-for="item in evidenceBindingRows" :key="item.binding_id" class="evidence-row">
                <div>
                  <span class="mono">{{ item.target_type }}</span>
                  <b>{{ item.target_path }}</b>
                  <small>{{ item.source_snippet }}</small>
                </div>
                <em>{{ item.confidence }}</em>
              </div>
              <div v-if="evidenceBindingRows.length === 0" class="empty compact">No evidence bindings found.</div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Source Project</h2>
              <span class="subtle">MiroFish graph seed</span>
            </div>
            <div class="source-project">
              <div class="source-row">
                <span>Project</span>
                <b>{{ sourceProject.project_id || '-' }}</b>
              </div>
              <div class="source-row">
                <span>Graph</span>
                <b>{{ sourceProject.graph_id || '-' }}</b>
              </div>
              <p>{{ sourceProject.simulation_requirement || 'No project seed metadata found.' }}</p>
              <div class="object-list">
                <span v-for="name in sourceEntityTypes" :key="name" class="object-chip">{{ name }}</span>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Event Plan</h2>
              <span class="subtle">{{ eventPlan.planned_events_count || 0 }} planned</span>
            </div>
            <div class="plan-box">
              <div class="source-row">
                <span>Source</span>
                <b>{{ eventPlan.source || '-' }}</b>
              </div>
              <div class="source-row">
                <span>Strategy</span>
                <b>{{ eventPlan.strategy || '-' }}</b>
              </div>
              <div class="object-list">
                <span v-for="type in eventPlanTypes" :key="type" class="object-chip">{{ type }}</span>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Financial Plan</h2>
              <span class="subtle">{{ financialPlan.source || 'runtime' }}</span>
            </div>
            <div class="plan-box">
              <div class="source-row">
                <span>Call</span>
                <b>{{ money(financialPlan.capital_call_amount) }}</b>
              </div>
              <div class="source-row">
                <span>Invest</span>
                <b>{{ money(financialPlan.investment_amount) }}</b>
              </div>
              <div class="source-row">
                <span>Exit</span>
                <b>{{ money(financialPlan.liquidity_proceeds) }}</b>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Fund Terms</h2>
              <span class="subtle">governance rules</span>
            </div>
            <div class="plan-box">
              <div class="source-row">
                <span>Commit</span>
                <b>{{ money(fundTerms.lp_commitment) }}</b>
              </div>
              <div class="source-row">
                <span>Fee</span>
                <b>{{ percent(fundTerms.management_fee?.annual_rate) }} / year</b>
              </div>
              <div class="source-row">
                <span>IC</span>
                <b>{{ percent((fundTerms.voting_threshold?.threshold_percent || 0) / 100) }} threshold</b>
              </div>
              <div class="source-row">
                <span>Carry</span>
                <b>{{ percent(fundTerms.waterfall_rule?.gp_carry) }}</b>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Scenario Workspace</h2>
              <span class="subtle">{{ scenarioPatchStatus || 'editable terms' }}</span>
            </div>
            <div class="plan-box">
              <div class="workspace-controls">
                <label>
                  <span>Fee rate</span>
                  <input v-model="workspaceManagementFee" type="number" min="0" step="0.001">
                </label>
                <label>
                  <span>Reserve minimum</span>
                  <input v-model="workspaceReserveMinimum" type="number" min="0" step="1000">
                </label>
                <label>
                  <span>Distribution</span>
                  <input v-model="workspaceDistributionAmount" type="number" min="0" step="1000">
                </label>
              </div>
              <div class="workspace-actions">
                <button @click="previewScenarioPatch" :disabled="loading || !reportContext">Preview Patch</button>
                <button @click="commitScenarioPatchAndRerun" :disabled="loading || !scenarioPatchPreview?.changed_paths?.length">
                  Commit Patch & Rerun
                </button>
              </div>
              <div class="patch-preview" v-if="scenarioPatchPreview">
                <div class="source-row">
                  <span>Changes</span>
                  <b>{{ scenarioPatchPreview.changed_paths?.length || 0 }}</b>
                </div>
                <div class="source-row">
                  <span>Shortfall</span>
                  <b>{{ money(scenarioPatchPreview.impact_preview?.reserve_shortfall) }}</b>
                </div>
                <div class="source-row">
                  <span>Rerun</span>
                  <b>{{ scenarioPatchPreview.rerun_required ? 'required' : 'not needed' }}</b>
                </div>
                <div class="patch-row" v-for="item in scenarioPatchRows" :key="item.path">
                  <span>{{ item.path }}</span>
                  <b>{{ formatPatchValue(item.before) }} -> {{ formatPatchValue(item.after) }}</b>
                </div>
              </div>
              <p class="hint-note">manual_patch_requires_explicit_commit_before_rerun</p>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Revision Ledger</h2>
              <span class="subtle">{{ revisionLedger.current_revision_id || 'no revision' }}</span>
            </div>
            <div class="plan-box">
              <div class="source-row">
                <span>Current</span>
                <b>{{ revisionLedger.current_revision_id || '-' }}</b>
              </div>
              <div class="source-row">
                <span>Count</span>
                <b>{{ revisionRows.length }}</b>
              </div>
              <div v-for="item in revisionRows" :key="item.revision_id" class="revision-row">
                <div>
                  <span class="mono">{{ item.revision_id }}</span>
                  <b>{{ item.change_type }}</b>
                  <small>{{ item.summary }}</small>
                </div>
                <em>{{ item.changed_paths?.length || 0 }} changes</em>
              </div>
              <div v-if="revisionRows.length === 0" class="empty compact">No revision ledger found.</div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Proposed Fund Terms</h2>
              <span class="subtle">{{ proposedFundTerms.status || 'not committed' }}</span>
            </div>
            <div class="plan-box">
              <div v-for="item in proposedTermRows" :key="item.key" class="proposal-row term-row">
                <div>
                  <span>{{ item.label }}</span>
                  <b>{{ item.clause }}</b>
                  <small>{{ item.parameters }}</small>
                </div>
                <em>{{ item.confidence }}</em>
              </div>
              <div v-if="proposedTermRows.length === 0" class="empty compact">No term proposal generated.</div>
              <p class="hint-note">{{ proposedFundTerms.commit_policy || 'proposal_only_requires_user_confirmation' }}</p>
              <div class="object-list">
                <span v-for="sentence in fundTermSentences" :key="sentence" class="object-chip evidence-chip">{{ sentence }}</span>
              </div>
              <button class="commit-btn" @click="commitTermsAndRerun" :disabled="loading || !canCommitTerms">
                Commit Terms & Rerun
              </button>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Governance Controls</h2>
              <span class="subtle">reserve / default / audit</span>
            </div>
            <div class="plan-box">
              <div class="source-row">
                <span>Reserve</span>
                <b>{{ money(reserveSummary.required) }}</b>
              </div>
              <div class="source-row">
                <span>Shortfall</span>
                <b>{{ money(reserveSummary.shortfall) }}</b>
              </div>
              <div class="source-row">
                <span>Default</span>
                <b>{{ percent(fundTerms.default_remedies?.default_interest_annual_rate) }} interest</b>
              </div>
              <div class="source-row">
                <span>Audit</span>
                <b>{{ auditSummary.exceptions_count || 0 }} exceptions</b>
              </div>
              <div class="object-list">
                <span v-for="check in auditChecks" :key="check" class="object-chip">{{ check }}</span>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Proposed Plan</h2>
              <span class="subtle">{{ proposedFinancialPlan.status || 'not committed' }}</span>
            </div>
            <div class="plan-box">
              <div v-for="item in proposedPlanRows" :key="item.key" class="proposal-row">
                <div>
                  <span>{{ item.label }}</span>
                  <b>{{ money(item.value) }}</b>
                </div>
                <em>{{ item.confidence }}</em>
              </div>
              <div v-if="proposedPlanRows.length === 0" class="empty compact">No proposal generated.</div>
              <p class="hint-note">{{ proposedFinancialPlan.commit_policy || 'proposal_only_requires_user_confirmation' }}</p>
              <div class="object-list">
                <span v-for="item in parsedAmountRows" :key="item.raw" class="object-chip">
                  {{ item.raw }} = {{ money(item.normalized_amount) }}
                </span>
              </div>
              <button class="commit-btn" @click="commitProposalAndRerun" :disabled="loading || !canCommitProposal">
                Commit & Rerun
              </button>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Financial Hints</h2>
              <span class="subtle">not committed</span>
            </div>
            <div class="plan-box">
              <div class="object-list">
                <span v-for="amount in financialHintAmounts" :key="amount" class="object-chip">{{ amount }}</span>
              </div>
              <p class="hint-note">{{ financialHints.commit_policy || 'hints_only' }}</p>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Branch Results</h2>
              <span class="subtle">{{ branchRows.length }} branches</span>
            </div>
            <div class="risk-strip">
              <div v-for="item in branchRiskRows" :key="item.branch_id" class="risk-pill" :class="`risk-${item.risk_level}`">
                <span class="mono">{{ item.branch_id }}</span>
                <b>{{ item.risk_level }} {{ item.risk_score }}</b>
                <small>{{ item.primary_action }}</small>
              </div>
            </div>
            <div class="branch-list">
              <div v-for="branch in branchRows" :key="branch.branch_id" class="branch-row">
                <div class="branch-top">
                  <span class="branch-id mono">{{ branch.branch_id }}</span>
                  <span class="branch-status">{{ branch.status }} / {{ branch.governance?.risk_level || 'unknown' }}</span>
                </div>
                <p>{{ branch.summary }}</p>
                <div class="governance-box" v-if="branch.governance">
                  <div class="source-row">
                    <span>Risk</span>
                    <b>{{ branch.governance.risk_score }} / {{ branch.governance.risk_level }}</b>
                  </div>
                  <div class="object-list">
                    <span v-for="term in branch.governance.triggered_terms" :key="`${branch.branch_id}-${term}`" class="object-chip">{{ term }}</span>
                  </div>
                  <ul class="action-list">
                    <li v-for="action in branch.governance.governance_actions" :key="`${branch.branch_id}-${action}`">{{ action }}</li>
                  </ul>
                  <div class="object-list" v-if="branch.governance.audit_flags?.length">
                    <span v-for="flag in branch.governance.audit_flags" :key="flag.message" class="object-chip evidence-chip">{{ flag.severity }}: {{ flag.message }}</span>
                  </div>
                </div>
                <div class="impact-grid">
                  <span v-for="(value, key) in branch.financial_impact" :key="key">
                    <b>{{ key }}</b>
                    {{ formatImpact(value) }}
                  </span>
                </div>
              </div>
              <div v-if="branchRows.length === 0" class="empty">No branch results yet.</div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Audit Outputs</h2>
              <span class="subtle">{{ packetStatus || 'MiroFish replacement slot' }}</span>
            </div>
            <div class="packet-box" v-if="packetPreview">
              <div class="source-row">
                <span>Status</span>
                <b>{{ packetStatus }}</b>
              </div>
              <div class="source-row">
                <span>Review</span>
                <b>{{ reviewStatus }}</b>
              </div>
              <div class="source-row">
                <span>Revision</span>
                <b>{{ reviewRevisionLabel }}</b>
              </div>
              <div class="source-row">
                <span>Risk</span>
                <b>{{ packetRiskLabel }}</b>
              </div>
              <div class="review-actions">
                <button @click="submitReview('approve')" :disabled="loading || !packetStatus || packetIsStale">Approve</button>
                <button @click="submitReview('waive_reserve')" :disabled="loading || !packetStatus || packetIsStale">Waive Reserve</button>
                <button @click="submitReview('request_rerun')" :disabled="loading || !packetStatus">Request Rerun</button>
              </div>
              <p class="hint-note stale-note" v-if="packetIsStale">{{ reviewState.message }}</p>
              <div class="review-log" v-if="reviewLog.length">
                <span v-for="item in reviewLog" :key="`${item.action}-${item.created_at}`">
                  {{ item.action }} / {{ item.role }} / {{ item.created_at }}
                </span>
              </div>
              <pre class="memo-preview">{{ packetPreview }}</pre>
            </div>
            <div class="packet-box" v-if="meetingPackSummary.pack_type">
              <div class="source-row">
                <span>Meeting Pack</span>
                <b>{{ meetingPackSummary.pack_type }}</b>
              </div>
              <div class="source-row">
                <span>LP readiness</span>
                <b>{{ meetingPackSummary.lp_readiness_status || '-' }}</b>
              </div>
              <div class="source-row">
                <span>Agenda / Decisions / Evidence</span>
                <b>{{ meetingPackSummary.agenda_count }} / {{ meetingPackSummary.decision_count }} / {{ meetingPackSummary.evidence_count }}</b>
              </div>
              <div class="source-row">
                <span>DOCX / PDF</span>
                <b>{{ fileBytes(meetingPackSummary.files?.docx?.bytes) }} / {{ fileBytes(meetingPackSummary.files?.pdf?.bytes) }}</b>
              </div>
            </div>
            <div class="output-list">
              <button v-for="file in outputFiles" :key="file" @click="loadOutput(file)">
                {{ file }}
              </button>
            </div>
            <pre class="json-preview">{{ selectedOutputPreview }}</pre>
          </section>

          <section class="panel">
            <div class="panel-header">
              <h2>Remediation Plan</h2>
              <span class="subtle">{{ remediationPlan.status || 'not generated' }}</span>
            </div>
            <div class="plan-box">
              <div class="source-row">
                <span>Allowed</span>
                <b>{{ remediationPlan.adoption_allowed === false ? 'blocked' : remediationPlan.status ? 'yes' : '-' }}</b>
              </div>
              <div class="source-row">
                <span>Recommend</span>
                <b>{{ remediationPlan.recommended_option_id || '-' }}</b>
              </div>
              <div class="workspace-actions">
                <button @click="previewRecommendedRemediation" :disabled="loading || !canAdoptRecommendedRemediation">
                  Preview Recommended
                </button>
                <button @click="commitRecommendedRemediationAndRerun" :disabled="loading || !canAdoptRecommendedRemediation">
                  Commit Recommended & Rerun
                </button>
              </div>
              <p class="hint-note stale-note" v-if="remediationPlan.blocked_reason">{{ remediationPlan.blocked_reason }}</p>
              <div v-for="item in remediationOptions" :key="item.option_id" class="remediation-row">
                <div>
                  <span>{{ item.option_type }} / {{ item.owner }}</span>
                  <b>{{ item.option_id }}</b>
                  <small>{{ item.summary }}</small>
                </div>
                <em>{{ item.recommended ? 'recommended' : item.approval_required }}</em>
              </div>
              <div v-if="remediationOptions.length === 0" class="empty compact">No remediation plan generated.</div>
            </div>
          </section>
        </aside>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  commitBusinessFundTerms,
  commitBusinessFinancialPlan,
  commitBusinessGovernanceRemediationOption,
  commitBusinessScenarioPatch,
  generateBusinessGovernancePacket,
  generateBusinessGovernanceRemediationPlan,
  generateBusinessMeetingPack,
  generateBusinessReport,
  getBusinessAccessStatus,
  getBusinessGovernanceReview,
  getBusinessGovernanceRemediationPlan,
  getBusinessOutput,
  getBusinessReportContext,
  getBusinessScenarioRevisions,
  getBusinessSimulationStatus,
  previewBusinessGovernanceRemediationOption,
  previewBusinessScenarioPatch,
  runBusinessSimulation,
  updateBusinessGovernanceReview,
  verifyBusinessAccessCode
} from '../api/businessSimulation'

const route = useRoute()
const router = useRouter()

const currentSimulationId = computed(() => route.params.simulationId || 'demo_business')
const configuredAccessCode = (import.meta.env.VITE_BUSINESS_DEMO_PASSWORD || '').trim()
const accessCodeSessionKey = 'mirofish_business_demo_access_code'
const accessChecking = ref(true)
const accessStatus = ref(null)
const requiresAccess = computed(() => accessStatus.value?.access_required ?? Boolean(configuredAccessCode))
const accessGranted = ref(false)
const accessProfile = ref(null)
const accessCode = ref('')
const accessError = ref('')
const loading = ref(false)
const error = ref('')
const runStatus = ref(null)
const reportContext = ref(null)
const branchResults = ref(null)
const reportMarkdown = ref('')
const reportBytes = ref(0)
const packetPreview = ref('')
const packetStatus = ref('')
const packetRiskLabel = ref('')
const reviewState = ref(null)
const meetingPackSummary = ref({})
const remediationPlan = ref({})
const selectedOutputPreview = ref('')
const revisionLedger = ref({})
const workspaceManagementFee = ref('')
const workspaceReserveMinimum = ref('')
const workspaceDistributionAmount = ref('')
const scenarioPatchPreview = ref(null)
const scenarioPatchStatus = ref('')

const outputFiles = [
  'event_log.jsonl',
  'ledger.jsonl',
  'decision_records.jsonl',
  'rule_execution_records.jsonl',
  'branch_results.json',
  'state_snapshot.json',
  'report_context.json',
  'business_report.md',
  'governance_packet.json',
  'governance_memo.md',
  'governance_review.json',
  'governance_remediation_plan.json',
  'meeting_pack.json',
  'meeting_pack.md',
  'evidence_bindings.json',
  'scenario_patch.json',
  'scenario_revisions.json'
]

const statusText = computed(() => {
  if (error.value) return 'error'
  return runStatus.value?.runner_status || 'ready'
})

const statusClass = computed(() => {
  if (error.value) return 'error'
  return statusText.value === 'completed' ? 'completed' : 'ready'
})

const timeline = computed(() => reportContext.value?.timeline || [])
const cashflow = computed(() => reportContext.value?.cashflow_summary || {})
const sourceProject = computed(() => reportContext.value?.source_project || {})
const sourceEntityTypes = computed(() => (sourceProject.value.ontology_entity_types || []).slice(0, 8))
const objectNameMap = computed(() => reportContext.value?.object_name_map || {})
const eventPlan = computed(() => reportContext.value?.event_plan_summary || {})
const eventPlanTypes = computed(() => (eventPlan.value.planned_event_types || []).slice(0, 10))
const financialPlan = computed(() => reportContext.value?.financial_plan || {})
const fundTerms = computed(() => reportContext.value?.fund_terms_summary || {})
const lifecycle = computed(() => reportContext.value?.fund_lifecycle_summary || {})
const capitalCallSchedule = computed(() => reportContext.value?.capital_call_schedule || lifecycle.value.capital_call_schedule || [])
const navSnapshots = computed(() => reportContext.value?.nav_snapshots || lifecycle.value.nav_snapshots || [])
const lpReadiness = computed(() => reportContext.value?.lp_readiness_summary || lifecycle.value.lp_readiness_summary || {})
const lpReadinessItems = computed(() => lpReadiness.value?.items || [])
const evidenceBindings = computed(() => reportContext.value?.evidence_bindings || {})
const evidenceBindingRows = computed(() => (evidenceBindings.value?.bindings || []).slice(0, 8))
const evidenceBindingCount = computed(() => evidenceBindings.value?.bindings_count || evidenceBindingRows.value.length)
const governanceSummary = computed(() => reportContext.value?.governance_summary || {})
const reserveSummary = computed(() => reportContext.value?.reserve_summary || {})
const auditSummary = computed(() => reportContext.value?.audit_summary || {})
const auditChecks = computed(() => auditSummary.value.last_review?.required_checks || fundTerms.value.audit_review?.required_checks || [])
const proposedFundTerms = computed(() => reportContext.value?.proposed_fund_terms || {})
const proposedTermRows = computed(() => {
  const labels = {
    management_fee: 'Fee',
    voting_threshold: 'IC',
    preferred_return: 'Preferred',
    gp_carry: 'Carry',
    default_remedies: 'Default',
    reserve_account: 'Reserve',
    audit_review: 'Audit'
  }
  return Object.entries(proposedFundTerms.value.proposals || {}).map(([key, value]) => ({
    key,
    label: labels[key] || key,
    clause: value.clause_type || key,
    parameters: formatParameters(value.parameters || {}),
    confidence: value.confidence || 'unknown'
  }))
})
const fundTermHints = computed(() => sourceProject.value.fund_term_hints || proposedFundTerms.value.hints || {})
const fundTermSentences = computed(() => (fundTermHints.value.sentences || []).slice(0, 4))
const canCommitTerms = computed(() => {
  return proposedTermRows.value.length > 0 && proposedFundTerms.value.status !== 'committed_to_rules'
})
const proposedFinancialPlan = computed(() => reportContext.value?.proposed_financial_plan || {})
const proposedPlanRows = computed(() => {
  const labels = {
    lp_commitment: 'Commit',
    capital_call_amount: 'Call',
    investment_amount: 'Invest',
    liquidity_proceeds: 'Exit',
    distribution_amount: 'Distribute'
  }
  return Object.entries(proposedFinancialPlan.value.proposals || {}).map(([key, value]) => ({
    key,
    label: labels[key] || key,
    value: value.value,
    confidence: value.confidence || 'unknown'
  }))
})
const parsedAmountRows = computed(() => (proposedFinancialPlan.value.parsed_amounts || []).slice(0, 6))
const canCommitProposal = computed(() => {
  return proposedPlanRows.value.length > 0 && proposedFinancialPlan.value.status !== 'committed_to_financial_plan'
})
const financialHints = computed(() => sourceProject.value.financial_hints || {})
const financialHintAmounts = computed(() => (financialHints.value.amounts || []).slice(0, 8))
const ledgerBalanced = computed(() => {
  const finding = reportContext.value?.executive_findings?.find((item) => item.includes('Ledger balanced'))
  return finding?.includes('True') ? 'Balanced' : '-'
})
const auditStatus = computed(() => {
  if (!reportContext.value) return '-'
  return Number(governanceSummary.value.audit_exceptions || 0) === 0 ? 'Clear' : `${governanceSummary.value.audit_exceptions} issues`
})
const branchRiskRows = computed(() => reportContext.value?.branch_risk_summary || branchResults.value?.risk_summary || [])
const reviewStatus = computed(() => {
  if (!reviewState.value) return 'not generated'
  const status = reviewState.value.effective_review_status || reviewState.value.review_status
  return reviewState.value.requires_rerun ? `${status} / rerun` : status
})
const packetIsStale = computed(() => Boolean(reviewState.value?.packet_is_stale))
const reviewRevisionLabel = computed(() => {
  if (!reviewState.value) return '-'
  const packetRevision = reviewState.value.packet_revision_id || reviewState.value.scenario_revision_id || '-'
  const currentRevision = reviewState.value.current_revision_id || '-'
  return packetRevision === currentRevision ? packetRevision : `${packetRevision} -> ${currentRevision}`
})
const reviewLog = computed(() => (reviewState.value?.review_log || []).slice(-4).reverse())
const revisionRows = computed(() => (revisionLedger.value?.revisions || []).slice(-5).reverse())
const remediationOptions = computed(() => remediationPlan.value?.options || [])
const recommendedRemediationOption = computed(() => {
  return remediationOptions.value.find((item) => item.option_id === remediationPlan.value?.recommended_option_id) || null
})
const canAdoptRecommendedRemediation = computed(() => {
  return remediationPlan.value?.adoption_allowed !== false && recommendedRemediationOption.value?.option_type === 'scenario_patch'
})
const scenarioPatchRows = computed(() => (scenarioPatchPreview.value?.changed_paths || []).slice(0, 8))

const branchRows = computed(() => {
  const branches = branchResults.value?.branches || reportContext.value?.branch_results?.branches || {}
  return Object.entries(branches).map(([branch_id, value]) => ({
    branch_id,
    ...value
  }))
})

const money = (value) => {
  const amount = Number(value || 0)
  return amount.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

const fileBytes = (value) => {
  const bytes = Number(value || 0)
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

const percent = (value) => {
  const amount = Number(value || 0)
  return `${(amount * 100).toLocaleString('en-US', { maximumFractionDigits: 2 })}%`
}

const multiple = (value) => {
  const amount = Number(value || 0)
  return `${amount.toLocaleString('en-US', { maximumFractionDigits: 2 })}x`
}

const formatParameters = (value) => {
  return Object.entries(value)
    .map(([key, item]) => `${key}: ${typeof item === 'number' ? item.toLocaleString('en-US', { maximumFractionDigits: 4 }) : item}`)
    .join(' | ')
}

const formatImpact = (value) => {
  if (typeof value === 'number') return money(value)
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return value
}

const objectLabel = (ref) => objectNameMap.value[ref] || ref

const syncScenarioWorkspace = () => {
  workspaceManagementFee.value = fundTerms.value.management_fee?.annual_rate ?? ''
  workspaceReserveMinimum.value = fundTerms.value.reserve_account?.minimum_cash ?? ''
  workspaceDistributionAmount.value = financialPlan.value.distribution_amount ?? ''
}

const buildScenarioPatchPayload = () => {
  const patch = { financial_plan: {}, fund_terms: {} }
  if (workspaceDistributionAmount.value !== '') {
    patch.financial_plan.distribution_amount = Number(workspaceDistributionAmount.value)
  }
  patch.fund_terms.management_fee = {}
  if (workspaceManagementFee.value !== '') {
    patch.fund_terms.management_fee.annual_rate = Number(workspaceManagementFee.value)
  }
  patch.fund_terms.reserve_account = {}
  if (workspaceReserveMinimum.value !== '') {
    patch.fund_terms.reserve_account.minimum_cash = Number(workspaceReserveMinimum.value)
  }
  return { patch }
}

const formatPatchValue = (value) => {
  if (typeof value === 'number') return value.toLocaleString('en-US', { maximumFractionDigits: 4 })
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (value === null || value === undefined) return '-'
  return String(value)
}

const loadAll = async () => {
  loading.value = true
  error.value = ''
  try {
    const statusRes = await getBusinessSimulationStatus(currentSimulationId.value).catch(() => ({ data: null }))
    runStatus.value = statusRes.data

    if (runStatus.value?.runner_status !== 'completed') {
      reportContext.value = null
      branchResults.value = null
      reportMarkdown.value = ''
      reportBytes.value = 0
      meetingPackSummary.value = {}
      return
    }

    const [contextRes, branchRes, revisionRes, meetingPackRes] = await Promise.all([
      getBusinessReportContext(currentSimulationId.value).catch(() => ({ data: null })),
      getBusinessOutput(currentSimulationId.value, 'branch_results.json').catch(() => ({ data: null })),
      getBusinessScenarioRevisions(currentSimulationId.value).catch(() => ({ data: null })),
      getBusinessOutput(currentSimulationId.value, 'meeting_pack.json').catch(() => ({ data: null }))
    ])

    reportContext.value = contextRes.data
    branchResults.value = branchRes.data
    revisionLedger.value = revisionRes.data || {}
    meetingPackSummary.value = meetingPackRes.data
      ? {
          pack_type: meetingPackRes.data.pack_type,
          lp_readiness_status: meetingPackRes.data.lp_capital_brief?.lp_readiness_status,
          agenda_count: meetingPackRes.data.meeting?.agenda?.length || 0,
          decision_count: meetingPackRes.data.decision_table?.length || 0,
          evidence_count: meetingPackRes.data.evidence_appendix?.length || 0,
          files: {}
        }
      : {}
    syncScenarioWorkspace()

    const reportRes = await getBusinessOutput(currentSimulationId.value, 'business_report.md')
    reportMarkdown.value = reportRes.data?.content || ''
    reportBytes.value = reportRes.data?.bytes || 0
    const reviewRes = await getBusinessGovernanceReview(currentSimulationId.value).catch(() => ({ data: null }))
    reviewState.value = reviewRes.data
    const remediationRes = await getBusinessGovernanceRemediationPlan(currentSimulationId.value).catch(() => ({ data: null }))
    remediationPlan.value = remediationRes.data || {}
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const previewScenarioPatch = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await previewBusinessScenarioPatch(currentSimulationId.value, buildScenarioPatchPayload())
    scenarioPatchPreview.value = res.data
    scenarioPatchStatus.value = res.data?.rerun_required ? 'preview ready' : 'no changes'
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const commitScenarioPatchAndRerun = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await commitBusinessScenarioPatch(currentSimulationId.value, buildScenarioPatchPayload())
    scenarioPatchPreview.value = res.data
    scenarioPatchStatus.value = 'committed'
    await runBusinessSimulation(currentSimulationId.value)
    await loadAll()
    await buildReport()
    await buildGovernancePacket()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const runDemo = async () => {
  loading.value = true
  error.value = ''
  try {
    await runBusinessSimulation(currentSimulationId.value)
    await loadAll()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const buildReport = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await generateBusinessReport(currentSimulationId.value)
    reportMarkdown.value = res.data?.preview || ''
    reportBytes.value = res.data?.bytes || 0
    const full = await getBusinessOutput(currentSimulationId.value, 'business_report.md')
    reportMarkdown.value = full.data?.content || reportMarkdown.value
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const buildGovernancePacket = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await generateBusinessGovernancePacket(currentSimulationId.value)
    packetPreview.value = res.data?.preview || ''
    packetStatus.value = res.data?.decision_status || ''
    reviewState.value = {
      review_status: res.data?.review_status || 'pending_review',
      effective_review_status: res.data?.review_status || 'pending_review',
      scenario_revision_id: res.data?.scenario_revision_id || '',
      packet_revision_id: res.data?.scenario_revision_id || '',
      current_revision_id: res.data?.scenario_revision_id || '',
      packet_is_stale: Boolean(res.data?.packet_is_stale),
      review_log: []
    }
    const highest = res.data?.highest_risk_branch || {}
    packetRiskLabel.value = highest.branch_id ? `${highest.branch_id} / ${highest.risk_level} ${highest.risk_score}` : '-'
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const buildMeetingPack = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await generateBusinessMeetingPack(currentSimulationId.value)
    meetingPackSummary.value = res.data || {}
    const full = await getBusinessOutput(currentSimulationId.value, 'meeting_pack.md')
    selectedOutputPreview.value = full.data?.content || res.data?.preview || ''
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const buildRemediationPlan = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await generateBusinessGovernanceRemediationPlan(currentSimulationId.value)
    remediationPlan.value = res.data?.preview || {}
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const previewRecommendedRemediation = async () => {
  if (!recommendedRemediationOption.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await previewBusinessGovernanceRemediationOption(
      currentSimulationId.value,
      recommendedRemediationOption.value.option_id
    )
    scenarioPatchPreview.value = res.data
    scenarioPatchStatus.value = res.data?.rerun_required ? 'remediation preview ready' : 'no changes'
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const commitRecommendedRemediationAndRerun = async () => {
  if (!recommendedRemediationOption.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await commitBusinessGovernanceRemediationOption(
      currentSimulationId.value,
      recommendedRemediationOption.value.option_id
    )
    scenarioPatchPreview.value = res.data
    scenarioPatchStatus.value = 'remediation committed'
    await runBusinessSimulation(currentSimulationId.value)
    await loadAll()
    await buildReport()
    await buildGovernancePacket()
    await buildRemediationPlan()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const submitReview = async (action) => {
  loading.value = true
  error.value = ''
  try {
    const res = await updateBusinessGovernanceReview(currentSimulationId.value, {
      action,
      actor: 'MiroFish reviewer',
      role: action === 'waive_reserve' ? 'LPAC' : 'GP'
    })
    reviewState.value = res.data?.review
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const commitProposalAndRerun = async () => {
  loading.value = true
  error.value = ''
  try {
    await commitBusinessFinancialPlan(currentSimulationId.value)
    await runBusinessSimulation(currentSimulationId.value)
    await loadAll()
    await buildReport()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const commitTermsAndRerun = async () => {
  loading.value = true
  error.value = ''
  try {
    await commitBusinessFundTerms(currentSimulationId.value)
    await runBusinessSimulation(currentSimulationId.value)
    await loadAll()
    await buildReport()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const loadOutput = async (file) => {
  try {
    const res = await getBusinessOutput(currentSimulationId.value, file)
    selectedOutputPreview.value = file.endsWith('.md')
      ? res.data.content
      : JSON.stringify(res.data, null, 2)
  } catch (err) {
    selectedOutputPreview.value = err.message
  }
}

const unlockBusinessDemo = async () => {
  if (!requiresAccess.value) {
    accessGranted.value = true
    return
  }
  const enteredCode = accessCode.value.trim()
  if (!enteredCode) {
    accessError.value = 'Enter the access code provided by the project owner.'
    return
  }
  try {
    const res = await verifyBusinessAccessCode(enteredCode, 'demo')
    sessionStorage.setItem(accessCodeSessionKey, enteredCode)
    accessGranted.value = true
    accessProfile.value = res.data?.code || null
    accessError.value = ''
    await loadAll()
    if (!reportContext.value) {
      await runDemo()
    }
    return
  } catch (err) {
    if (configuredAccessCode && enteredCode === configuredAccessCode) {
      sessionStorage.setItem(accessCodeSessionKey, enteredCode)
      accessGranted.value = true
      accessError.value = ''
      await loadAll()
      if (!reportContext.value) {
        await runDemo()
      }
      return
    }
    accessError.value = err.message || 'Access code does not match. Please ask the project owner for the current beta code.'
  }
}

const initializeAccess = async () => {
  accessChecking.value = true
  try {
    const statusRes = await getBusinessAccessStatus()
    accessStatus.value = statusRes.data
  } catch (err) {
    accessStatus.value = {
      access_required: Boolean(configuredAccessCode),
      warning: err.message
    }
  }

  if (!requiresAccess.value) {
    accessGranted.value = true
    accessChecking.value = false
    return
  }

  const storedCode = sessionStorage.getItem(accessCodeSessionKey)
  if (storedCode) {
    try {
      const verifyRes = await verifyBusinessAccessCode(storedCode, 'demo')
      accessGranted.value = true
      accessProfile.value = verifyRes.data?.code || null
    } catch {
      sessionStorage.removeItem(accessCodeSessionKey)
      accessGranted.value = false
    }
  }

  accessChecking.value = false
}

onMounted(async () => {
  await initializeAccess()
  if (requiresAccess.value && !accessGranted.value) return
  await loadAll()
  if (!reportContext.value) {
    await runDemo()
  }
})
</script>

<style scoped>
.business-view {
  min-height: 100vh;
  background: #f7f7f5;
  color: #111;
  font-family: 'JetBrains Mono', 'Space Grotesk', 'Noto Sans SC', monospace;
}

.access-view {
  display: grid;
  place-items: center;
  padding: 24px;
}

.access-panel {
  width: min(520px, 100%);
  border: 1px solid #d8d8cf;
  background: #fff;
  padding: 28px;
  display: grid;
  gap: 14px;
}

.access-brand {
  font-weight: 800;
  letter-spacing: 0;
  color: #111;
}

.access-panel h1 {
  margin: 0;
  font-size: 24px;
  letter-spacing: 0;
}

.access-panel p {
  margin: 0;
  line-height: 1.55;
  color: #444;
  font-size: 13px;
}

.access-form {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}

.access-form input {
  border: 1px solid #cfcfc7;
  padding: 10px 12px;
  font: inherit;
  min-width: 0;
}

.access-form button {
  border: 1px solid #111;
  background: #111;
  color: #fff;
  padding: 10px 14px;
  cursor: pointer;
}

.access-error {
  color: #9b1c1c !important;
  font-weight: 600;
}

.access-note {
  border-top: 1px solid #e8e8e1;
  padding-top: 12px;
  font-size: 12px !important;
}

.topbar {
  min-height: 64px;
  background: #111;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 24px;
}

.brand,
.ghost-btn,
.primary-btn {
  border: 1px solid currentColor;
  background: transparent;
  color: inherit;
  height: 36px;
  padding: 0 14px;
  cursor: pointer;
  font: inherit;
}

.brand {
  font-weight: 800;
  letter-spacing: 1px;
  border: 0;
}

.status-strip,
.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.pill,
.status {
  border: 1px solid rgba(255, 255, 255, 0.3);
  padding: 5px 8px;
  font-size: 12px;
}

.status.completed {
  background: #d8f3dc;
  color: #0f5132;
  border-color: #d8f3dc;
}

.status.error {
  background: #f8d7da;
  color: #842029;
  border-color: #f8d7da;
}

.primary-btn {
  background: #ff5a1f;
  border-color: #ff5a1f;
  color: #fff;
}

.workspace {
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
}

.summary-band {
  display: grid;
  grid-template-columns: repeat(6, minmax(128px, 1fr));
  gap: 1px;
  background: #d8d8d2;
  border: 1px solid #d8d8d2;
  margin-bottom: 20px;
}

.metric {
  background: #fff;
  padding: 18px;
  min-height: 88px;
}

.label,
.subtle {
  display: block;
  font-size: 12px;
  color: #6b6b63;
}

.value {
  display: block;
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(360px, 0.9fr);
  gap: 20px;
}

.main-column,
.side-column {
  display: grid;
  gap: 20px;
  align-content: start;
}

.panel {
  background: #fff;
  border: 1px solid #d8d8d2;
}

.panel-header {
  min-height: 54px;
  padding: 14px 16px;
  border-bottom: 1px solid #e5e5df;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

h2 {
  font-size: 15px;
  font-weight: 700;
}

.timeline {
  padding: 8px 16px 16px;
}

.timeline-row {
  display: grid;
  grid-template-columns: 112px 1fr;
  border-bottom: 1px solid #eee;
  padding: 14px 0;
  gap: 16px;
}

.date {
  font-size: 12px;
  color: #6b6b63;
}

.event-title {
  font-weight: 700;
  margin-bottom: 6px;
}

.event-body p,
.branch-row p {
  color: #333;
  line-height: 1.5;
  margin-bottom: 8px;
}

.object-list {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.object-chip {
  background: #f0f0ec;
  border: 1px solid #deded8;
  padding: 3px 6px;
  font-size: 11px;
  max-width: 220px;
  overflow-wrap: anywhere;
  line-height: 1.35;
}

.branch-list {
  padding: 12px;
  display: grid;
  gap: 12px;
}

.risk-strip {
  padding: 12px;
  border-bottom: 1px solid #e5e5df;
  display: grid;
  gap: 8px;
}

.risk-pill {
  border: 1px solid #deded8;
  background: #fafaf7;
  padding: 8px;
  display: grid;
  gap: 4px;
}

.risk-pill b,
.risk-pill small {
  overflow-wrap: anywhere;
}

.risk-pill small {
  color: #6b6b63;
  font-size: 11px;
  line-height: 1.35;
}

.risk-high,
.risk-critical {
  border-color: #f1a07b;
  background: #fff3ed;
}

.risk-medium {
  border-color: #e0c76d;
  background: #fff9dd;
}

.branch-row {
  border: 1px solid #e2e2dc;
  padding: 12px;
}

.branch-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.branch-status {
  font-size: 11px;
  color: #ff5a1f;
}

.impact-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  font-size: 11px;
}

.impact-grid span {
  background: #fafaf7;
  padding: 6px;
}

.impact-grid b {
  display: block;
  color: #6b6b63;
  font-weight: 500;
  margin-bottom: 3px;
}

.governance-box {
  border: 1px solid #e2e2dc;
  background: #fbfbf7;
  padding: 8px;
  display: grid;
  gap: 8px;
  margin-bottom: 8px;
}

.action-list {
  margin: 0;
  padding-left: 18px;
  color: #333;
  font-size: 12px;
  line-height: 1.45;
}

.output-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
  padding: 12px;
}

.packet-box {
  padding: 12px;
  border-bottom: 1px solid #e5e5df;
  display: grid;
  gap: 8px;
}

.memo-preview {
  max-height: 220px;
  overflow: auto;
  background: #111;
  color: #f7f7f5;
  padding: 10px;
  white-space: pre-wrap;
  font-size: 11px;
  line-height: 1.45;
}

.review-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.review-actions button {
  border: 1px solid #111;
  background: #fff;
  min-height: 32px;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.review-log {
  display: grid;
  gap: 4px;
  font-size: 11px;
  color: #6b6b63;
}

.review-log span {
  overflow-wrap: anywhere;
}

.source-project,
.plan-box {
  padding: 14px;
  display: grid;
  gap: 10px;
}

.source-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 10px;
  font-size: 12px;
}

.source-row span {
  color: #6b6b63;
}

.source-row b {
  overflow-wrap: anywhere;
}

.proposal-row {
  border: 1px solid #e2e2dc;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.proposal-row span,
.proposal-row em {
  display: block;
  color: #6b6b63;
  font-size: 11px;
  font-style: normal;
}

.proposal-row b {
  display: block;
  margin-top: 3px;
  font-size: 14px;
  overflow-wrap: anywhere;
}

.proposal-row small {
  display: block;
  margin-top: 4px;
  color: #333;
  font-size: 11px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.term-row {
  align-items: flex-start;
}

.revision-row {
  border: 1px solid #e2e2dc;
  padding: 8px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.revision-row span,
.revision-row em {
  display: block;
  color: #6b6b63;
  font-size: 11px;
  font-style: normal;
}

.revision-row b,
.revision-row small {
  display: block;
  overflow-wrap: anywhere;
}

.revision-row b {
  margin-top: 3px;
  font-size: 13px;
}

.revision-row small {
  margin-top: 4px;
  color: #333;
  font-size: 11px;
  line-height: 1.35;
}

.capital-call-row,
.readiness-row,
.nav-row,
.evidence-row {
  border: 1px solid #e2e2dc;
  padding: 8px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: flex-start;
  gap: 10px;
}

.capital-call-row span,
.capital-call-row em,
.readiness-row em,
.nav-row span,
.nav-row em,
.evidence-row span,
.evidence-row em {
  display: block;
  color: #6b6b63;
  font-size: 11px;
  font-style: normal;
}

.capital-call-row b,
.capital-call-row small,
.readiness-row b,
.readiness-row small,
.nav-row b,
.evidence-row b,
.evidence-row small {
  display: block;
  overflow-wrap: anywhere;
}

.capital-call-row b,
.nav-row b,
.evidence-row b {
  margin-top: 3px;
  font-size: 13px;
}

.capital-call-row small,
.readiness-row small,
.evidence-row small {
  margin-top: 4px;
  color: #333;
  font-size: 11px;
  line-height: 1.35;
}

.object-chip.warn {
  border-color: #c67b2f;
  color: #7c3d00;
  background: #fff6ea;
}

.remediation-row {
  border: 1px solid #e2e2dc;
  padding: 8px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.remediation-row span,
.remediation-row em {
  display: block;
  color: #6b6b63;
  font-size: 11px;
  font-style: normal;
}

.remediation-row b,
.remediation-row small {
  display: block;
  overflow-wrap: anywhere;
}

.remediation-row b {
  margin-top: 3px;
  font-size: 13px;
}

.remediation-row small {
  margin-top: 4px;
  color: #333;
  font-size: 11px;
  line-height: 1.35;
}

.evidence-chip {
  max-width: 100%;
}

.commit-btn {
  border: 1px solid #111;
  background: #111;
  color: #fff;
  height: 34px;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.workspace-controls {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.workspace-controls label {
  display: grid;
  gap: 5px;
  font-size: 11px;
  color: #6b6b63;
}

.workspace-controls input {
  width: 100%;
  min-width: 0;
  height: 34px;
  border: 1px solid #d8d8d2;
  background: #fff;
  color: #111;
  padding: 0 8px;
  font: inherit;
  font-size: 12px;
}

.workspace-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.workspace-actions button {
  border: 1px solid #111;
  background: #fff;
  min-height: 34px;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.workspace-actions button:last-child {
  background: #111;
  color: #fff;
}

.patch-preview {
  border: 1px solid #e2e2dc;
  background: #fbfbf7;
  padding: 8px;
  display: grid;
  gap: 6px;
}

.patch-row {
  border-top: 1px solid #e8e8e1;
  padding-top: 6px;
  display: grid;
  gap: 3px;
  font-size: 11px;
}

.patch-row span {
  color: #6b6b63;
  overflow-wrap: anywhere;
}

.patch-row b {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.source-project p {
  margin: 0;
  color: #333;
  line-height: 1.5;
  font-size: 12px;
  max-height: 130px;
  overflow: auto;
}

.hint-note {
  margin: 0;
  color: #6b6b63;
  font-size: 11px;
  overflow-wrap: anywhere;
}

.output-list button {
  text-align: left;
  background: #fff;
  border: 1px solid #e2e2dc;
  padding: 8px;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.json-preview,
.report-preview {
  margin: 0;
  padding: 14px;
  background: #111;
  color: #f7f7f5;
  overflow: auto;
  max-height: 460px;
  white-space: pre-wrap;
  font-size: 12px;
  line-height: 1.5;
}

.empty {
  padding: 24px;
  color: #777;
}

.empty.compact {
  padding: 8px;
  font-size: 12px;
}

.mono {
  font-variant-numeric: tabular-nums;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 1000px) {
  .topbar,
  .content-grid {
    grid-template-columns: 1fr;
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .summary-band {
    grid-template-columns: 1fr 1fr;
  }

  .workspace-controls {
    grid-template-columns: 1fr;
  }

  .content-grid {
    display: block;
  }

  .side-column {
    margin-top: 20px;
  }

  .access-form {
    grid-template-columns: 1fr;
  }
}
</style>
