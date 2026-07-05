<template>
  <div class="admin-view">
    <header class="admin-topbar">
      <button class="brand" @click="router.push('/')">MiroFish Fund Governance Edition</button>
      <div class="top-actions">
        <button @click="router.push({ name: 'BusinessSimulation', params: { simulationId: 'demo_business' } })">Demo</button>
        <button @click="refresh" :disabled="loading || !ownerUnlocked">Refresh</button>
      </div>
    </header>

    <main class="admin-shell">
      <section v-if="!ownerUnlocked" class="owner-gate">
        <div class="eyebrow">Owner Console</div>
        <h1>Access Code Management</h1>
        <p>Enter the owner code from your local environment to manage private beta groups.</p>
        <form class="owner-form" @submit.prevent="unlockOwner">
          <input v-model="ownerCode" type="password" autocomplete="current-password" placeholder="Owner code" />
          <button type="submit">Unlock</button>
        </form>
        <p v-if="error" class="error">{{ error }}</p>
        <p class="fine-print">Real trial codes and owner codes should stay in .env, .env.local, deployment secrets, or the gitignored private directory.</p>
      </section>

      <template v-else>
        <section class="summary-strip">
          <div>
            <span>Edition</span>
            <b>{{ accessStatus.edition || 'Fund Governance Edition' }}</b>
          </div>
          <div>
            <span>Total Groups</span>
            <b>{{ accessStatus.registry?.code_count || 0 }}</b>
          </div>
          <div>
            <span>Active</span>
            <b>{{ accessStatus.registry?.active_count || 0 }}</b>
          </div>
          <div>
            <span>Console</span>
            <b>{{ accessStatus.owner_console_enabled ? 'enabled' : 'disabled' }}</b>
          </div>
        </section>

        <section class="admin-grid">
          <form class="create-panel" @submit.prevent="createCode">
            <h2>New Trial Group</h2>
            <label>
              Label
              <input v-model="form.label" placeholder="LP Alpha - Family Office A" />
            </label>
            <label>
              Group
              <input v-model="form.group" placeholder="LP_ALPHA" />
            </label>
            <label>
              Optional Custom Code
              <input v-model="form.code" placeholder="Leave blank to generate" />
            </label>
            <label>
              Expires At
              <input v-model="form.expires_at" type="date" />
            </label>
            <div class="scope-row">
              <label><input v-model="form.scopes" value="demo" type="checkbox" /> Demo</label>
              <label><input v-model="form.scopes" value="report" type="checkbox" /> Report</label>
              <label><input v-model="form.scopes" value="meeting_pack" type="checkbox" /> Meeting Pack</label>
            </div>
            <button class="primary" type="submit" :disabled="loading">Create Code</button>
            <div v-if="displayOnceCode" class="display-once">
              <span>Display once</span>
              <code>{{ displayOnceCode }}</code>
            </div>
          </form>

          <section class="codes-panel">
            <div class="panel-header">
              <h2>Trial Groups</h2>
              <span>{{ codes.length }} groups</span>
            </div>
            <div class="table">
              <div class="table-row table-head">
                <span>Label</span>
                <span>Group</span>
                <span>Scopes</span>
                <span>Status</span>
                <span>Uses</span>
                <span>Action</span>
              </div>
              <div v-for="item in codes" :key="item.code_id" class="table-row">
                <span>
                  <b>{{ item.label }}</b>
                  <small>{{ item.expires_at || 'no expiry' }}</small>
                </span>
                <span>{{ item.group }}</span>
                <span>{{ item.scopes.join(', ') }}</span>
                <span :class="{ disabled: item.status !== 'active' }">{{ item.status }}</span>
                <span>{{ item.uses }}</span>
                <button @click="toggleCode(item)" :disabled="loading">
                  {{ item.status === 'active' ? 'Disable' : 'Enable' }}
                </button>
              </div>
              <p v-if="codes.length === 0" class="empty">No access groups yet.</p>
            </div>
          </section>
        </section>

        <section class="audit-panel">
          <div class="panel-header">
            <h2>Recent Access Log</h2>
            <span>{{ auditLog.length }} events</span>
          </div>
          <div class="audit-list">
            <div v-for="event in auditLog" :key="event.event_id" class="audit-row">
              <span>{{ event.created_at }}</span>
              <b>{{ event.action }}</b>
              <em>{{ event.status }}</em>
              <small>{{ event.group || '-' }} / {{ event.label || '-' }}</small>
            </div>
            <p v-if="auditLog.length === 0" class="empty">No access activity yet.</p>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createBusinessAccessCode,
  getBusinessAccessAudit,
  listBusinessAccessCodes,
  updateBusinessAccessCode
} from '../api/businessSimulation'

const router = useRouter()
const ownerSessionKey = 'mirofish_business_demo_owner_code'
const ownerCode = ref('')
const ownerUnlocked = ref(Boolean(sessionStorage.getItem(ownerSessionKey)))
const loading = ref(false)
const error = ref('')
const codes = ref([])
const auditLog = ref([])
const accessStatus = ref({})
const displayOnceCode = ref('')
const form = ref({
  label: '',
  group: 'LP_ALPHA',
  code: '',
  expires_at: '',
  scopes: ['demo', 'report', 'meeting_pack']
})

const unlockOwner = async () => {
  error.value = ''
  sessionStorage.setItem(ownerSessionKey, ownerCode.value.trim())
  ownerUnlocked.value = true
  try {
    await refresh()
  } catch (err) {
    sessionStorage.removeItem(ownerSessionKey)
    ownerUnlocked.value = false
    error.value = err.message || 'Owner code was rejected.'
  }
}

const refresh = async () => {
  loading.value = true
  error.value = ''
  try {
    const [codesRes, auditRes] = await Promise.all([
      listBusinessAccessCodes(),
      getBusinessAccessAudit(50)
    ])
    codes.value = codesRes.data?.codes || []
    accessStatus.value = codesRes.data?.access_status || {}
    auditLog.value = auditRes.data?.audit_log || []
  } catch (err) {
    error.value = err.message
    throw err
  } finally {
    loading.value = false
  }
}

const createCode = async () => {
  loading.value = true
  error.value = ''
  displayOnceCode.value = ''
  try {
    const res = await createBusinessAccessCode({
      label: form.value.label,
      group: form.value.group,
      code: form.value.code,
      expires_at: form.value.expires_at,
      scopes: form.value.scopes
    })
    displayOnceCode.value = res.data?.display_once_code || ''
    form.value.code = ''
    await refresh()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const toggleCode = async (item) => {
  loading.value = true
  error.value = ''
  try {
    await updateBusinessAccessCode(item.code_id, {
      status: item.status === 'active' ? 'disabled' : 'active'
    })
    await refresh()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (ownerUnlocked.value) {
    try {
      await refresh()
    } catch {
      sessionStorage.removeItem(ownerSessionKey)
      ownerUnlocked.value = false
    }
  }
})
</script>

<style scoped>
.admin-view {
  min-height: 100vh;
  background: #f6f6f3;
  color: #121212;
  font-family: 'Inter', 'Noto Sans TC', system-ui, sans-serif;
}

.admin-topbar {
  height: 64px;
  padding: 0 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #d9d7cf;
  background: #ffffff;
}

.brand {
  border: 0;
  background: transparent;
  font-weight: 800;
  font-size: 15px;
  color: #123052;
  cursor: pointer;
}

.top-actions {
  display: flex;
  gap: 10px;
}

button {
  border: 1px solid #123052;
  background: #ffffff;
  color: #123052;
  min-height: 36px;
  padding: 0 14px;
  font-weight: 700;
  cursor: pointer;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary,
.owner-form button {
  background: #123052;
  color: #ffffff;
}

.admin-shell {
  max-width: 1180px;
  margin: 0 auto;
  padding: 32px 24px 56px;
}

.owner-gate {
  max-width: 560px;
  margin-top: 64px;
}

.eyebrow,
.summary-strip span,
.panel-header span,
.display-once span {
  color: #6c746c;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 10px 0 16px;
  color: #123052;
}

.owner-form {
  display: flex;
  gap: 10px;
  margin-top: 22px;
}

input {
  min-height: 38px;
  border: 1px solid #c8c6bd;
  background: #ffffff;
  padding: 0 12px;
  font: inherit;
}

.owner-form input {
  flex: 1;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 22px;
}

.summary-strip div,
.create-panel,
.codes-panel,
.audit-panel {
  border: 1px solid #d7d4ca;
  background: #ffffff;
  padding: 18px;
}

.summary-strip b {
  display: block;
  margin-top: 8px;
  font-size: 20px;
}

.admin-grid {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 18px;
  align-items: start;
}

.create-panel label {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
  font-weight: 700;
  color: #29333f;
}

.scope-row {
  display: grid;
  gap: 8px;
  margin: 10px 0 18px;
}

.scope-row label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-weight: 600;
}

.scope-row input {
  min-height: auto;
}

.display-once {
  margin-top: 14px;
  padding: 12px;
  background: #f0f5ee;
  border: 1px solid #a6be98;
}

.display-once code {
  display: block;
  margin-top: 6px;
  overflow-wrap: anywhere;
  font-weight: 800;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.table-row {
  display: grid;
  grid-template-columns: 1.7fr 1fr 1.3fr 0.7fr 0.5fr 0.8fr;
  gap: 10px;
  align-items: center;
  padding: 12px 0;
  border-top: 1px solid #eceae3;
}

.table-head {
  color: #6c746c;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
  border-top: 0;
}

.table-row small {
  display: block;
  color: #737970;
  margin-top: 4px;
}

.disabled,
.error {
  color: #a33a2a;
}

.audit-panel {
  margin-top: 18px;
}

.audit-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 2fr;
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid #eceae3;
}

.audit-row span,
.audit-row small,
.audit-row em {
  color: #737970;
  font-style: normal;
}

.empty,
.fine-print {
  color: #737970;
}

@media (max-width: 900px) {
  .summary-strip,
  .admin-grid,
  .table-row,
  .audit-row {
    grid-template-columns: 1fr;
  }

  .owner-form {
    flex-direction: column;
  }
}
</style>
