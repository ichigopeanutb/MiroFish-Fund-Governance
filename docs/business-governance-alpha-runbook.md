# Business Governance Engine Alpha Runbook

## Local Services

Use the stable launcher when the page is meant to stay available:

```bash
npm run dev:stable start
npm run dev:stable status
npm run dev:stable restart
npm run dev:stable stop
```

The launcher writes runtime files under `.mirofish_runtime/`:

- `.mirofish_runtime/backend.pid`
- `.mirofish_runtime/frontend.pid`
- `.mirofish_runtime/logs/backend.log`
- `.mirofish_runtime/logs/frontend.log`

Backend is started with `FLASK_DEBUG=false` to avoid the Flask debug reloader
briefly dropping `127.0.0.1:5001`.

## Current Engine Contract

MiroFish remains the parent workflow:

1. Upload source documents.
2. Build ontology and graph.
3. Select `Business / Fund Governance`.
4. Create a business simulation from the MiroFish project.
5. Run the fund-governance simulation.
6. Review proposed financial terms.
7. Review proposed governance fund terms.
8. Commit and rerun only after explicit approval.

## Fund Terms Supported In Alpha

The engine reads these LPA clauses from `fund_terms.yaml`:

- `capital_call_notice`
- `voting_threshold`
- `management_fee`
- `default_remedies`
- `reserve_account`
- `waterfall_rule`
- `audit_review`

The alpha waterfall applies:

1. Return of capital to LP.
2. Preferred return to LP.
3. Remaining profit split between LP and GP carry.

## Terms Extraction / Scenario Authoring Alpha

When a business simulation is created from a MiroFish project, the backend now
extracts two proposal layers from project text:

- `proposed_financial_plan`: commitment, call amount, investment amount, exit proceeds, distribution amount.
- `proposed_fund_terms`: management fee, IC approval threshold, preferred return, GP carry, default remedies, reserve account, and audit materiality.

Both proposal layers are non-committing by default:

- Financial hints use `hints_only_not_committed_to_ledger`.
- Fund-term hints use `hints_only_not_committed_to_rules`.
- Proposals use `proposal_only_requires_user_confirmation`.

Commit routes:

```text
POST /api/business-simulation/:simulation_id/financial-plan/commit
POST /api/business-simulation/:simulation_id/fund-terms/commit
```

Commit routes update source YAML and set `pending_change`, but keep
`runner_status` compatible with the shared MiroFish runner state model. The
caller should rerun the simulation after either commit.

The UI exposes:

- `Proposed Plan` for financial proposals.
- `Proposed Fund Terms` for governance-rule proposals and source evidence.
- `Governance Controls` for reserve/default/audit status after rerun.
- `Branch Results` with risk level, score, triggered terms, governance actions, and audit flags.
- `Audit Outputs` can generate and inspect governance decision packet files.

## Scenario Branch Governance Alpha

Branch results now include a governance profile for each simulated branch:

- `risk_score`: deterministic score from capital non-payment, reserve shortfall, audit exceptions, deployment block, rejection, and delay.
- `risk_level`: `low`, `medium`, `high`, or `critical`.
- `triggered_terms`: clauses or governance controls implicated by the branch.
- `governance_actions`: practical next actions for GP/IC/LP reporting.
- `audit_flags`: reserve/audit issues that should be reviewed before distribution or reporting.

`branch_results.json` also includes top-level `risk_summary`, sorted from
highest to lowest risk. `report_context.json` mirrors this as
`branch_risk_summary`, and the markdown report includes a `Branch Risk Summary`
section.

## Verification Baseline

The current demo run produces:

- 15 business events.
- 5 ledger entries.
- 4 rule execution records.
- Balanced ledger.
- Management fee payment event.
- IC threshold rule.
- Reserve account review rule.
- Waterfall rule.
- Audit review with required checks.

The live smoke simulation used during development is:

```text
bus_terms_waterfall_smoke
```

Expected base cashflow:

- Capital called: `1,000,000`
- Management fee: `50,000`
- Required reserve: `250,000`
- Reserve shortfall: `0`
- LP distribution: `1,136,000`
- GP carry: `14,000`

Default-remedy branch terms:

- Default interest: `12%` annualized for `30` days.
- Cure period: `15` days.
- Voting rights suspended.
- New deployments blocked.

Expected branch-risk baseline:

- `lp_default`: `critical`, first in `risk_summary`.
- `base`: `low` in the clean demo.
- `base`: `medium` after a committed reserve policy creates a reserve shortfall.

## Governance Decision Packet Alpha

The API can generate LPAC/IC-ready decision materials from `report_context.json`:

```text
POST /api/business-simulation/:simulation_id/governance-packet
```

Generated files:

- `governance_packet.json`: structured decision packet for downstream tools.
- `governance_memo.md`: human-readable LPAC/IC memo.
- `governance_review.json`: human review state bound to a packet digest.

The packet includes:

- `decision_status`: `review_ready` or `action_required`.
- `highest_risk_branch`.
- `required_decisions`.
- `branch_actions`.
- `key_metrics`.
- `fund_terms_snapshot`.
- `evidence_index`.

The packet is deterministic and read-only with respect to simulation state. It
does not commit ledger, rule, or branch outcomes; it packages already-generated
event logs, ledger entries, rule records, branch results, and report context.

## Human Review / Approval Workflow Alpha

Review APIs:

```text
GET  /api/business-simulation/:simulation_id/governance-review
POST /api/business-simulation/:simulation_id/governance-review
```

Supported review actions:

- `approve`: closes the packet as approved.
- `waive_reserve`: records LPAC reserve waiver without changing ledger/rules.
- `request_rerun`: marks the packet as requiring scenario revision and rerun.
- `reject`: marks the packet rejected and requiring revision.
- `reset_pending`: returns review state to pending review.

Review state is bound to `governance_packet.json` by SHA-256 digest. If the
packet changes, the review state is reinitialized as `pending_review`. This
prevents approving a stale packet after rerun or packet regeneration.

## Editable Scenario / Terms Workspace Alpha

Manual scenario edits now use a patch-preview-commit loop:

```text
POST /api/business-simulation/:simulation_id/scenario-patch/preview
POST /api/business-simulation/:simulation_id/scenario-patch/commit
```

The preview route writes `scenario_patch.json` but does not change executable
state. The commit route updates `scenario.yaml` and `fund_terms.yaml`, records
the patch under `manual_scenario_patch`, writes `scenario_patch.json`, and sets
`pending_change` to `scenario_patch_committed`. The caller should rerun the
simulation, regenerate the report, and regenerate the governance packet.

Patchable alpha fields:

- `financial_plan`: `lp_commitment`, `capital_call_amount`, `investment_amount`, `liquidity_proceeds`, `distribution_amount`.
- `fund_terms.management_fee`: `annual_rate`, `basis`, `period_months`.
- `fund_terms.voting_threshold`: `matter`, `threshold_percent`.
- `fund_terms.waterfall_rule`: `return_of_capital`, `preferred_return_rate`, `preferred_return_months`, `gp_carry`, `lp_profit_split`.
- `fund_terms.default_remedies`: `default_interest_annual_rate`, `default_interest_days`, `cure_period_days`, `suspend_voting_rights`, `block_new_deployments`.
- `fund_terms.reserve_account`: `minimum_cash`, `rate_of_called_capital`, `review_before_distribution`.
- `fund_terms.audit_review`: `materiality_threshold`, `required_checks`.

Example payload:

```json
{
  "patch": {
    "financial_plan": {
      "distribution_amount": 3405000
    },
    "fund_terms": {
      "management_fee": {
        "annual_rate": 0.03
      },
      "reserve_account": {
        "minimum_cash": 800000
      }
    }
  }
}
```

The UI exposes this as `Scenario Workspace` with `Preview Patch` and
`Commit Patch & Rerun`.

## Scenario Revision Ledger Alpha

Every governance input commit now appends a version record to:

```text
scenario_revisions.json
```

Read API:

```text
GET /api/business-simulation/:simulation_id/scenario-revisions
```

Revision records are appended for:

- `initial_template`: simulation created from a MiroFish project seed.
- `fund_terms_commit`: proposed fund terms committed into LPA clauses.
- `financial_plan_commit`: proposed financial plan committed into executable scenario events.
- `manual_scenario_patch_commit`: editable workspace patch committed into scenario/fund terms.

Each revision stores:

- `revision_id` and `parent_revision_id`.
- `change_type`.
- `summary`.
- `changed_paths`.
- source metadata.
- SHA-256 file digests for `scenario.yaml`, `fund_terms.yaml`, and `business_simulation_config.json`.

This is a governance input revision ledger, not the financial accounting ledger.
It makes the simulator auditable by linking reports and governance packets back
to the exact terms/scenario version that generated them.

The UI exposes this as `Revision Ledger`, and `report_context.json` includes
`scenario_revision` after each run.

## Revision-Bound Governance Review Alpha

Governance packets and review state are now bound to the scenario revision that
generated them:

- `governance_packet.json` includes `scenario_revision.current_revision_id`.
- `governance_review.json` stores `scenario_revision_id`.
- `GET /api/business-simulation/:simulation_id/governance-review` returns:
  - `packet_revision_id`
  - `current_revision_id`
  - `packet_is_stale`
  - `effective_review_status`

If a scenario/fund-term commit creates a newer revision after a packet was
generated, the old packet becomes stale. Stale packets can still be inspected,
but approval actions are blocked:

- `approve`: blocked with HTTP `409`.
- `waive_reserve`: blocked with HTTP `409`.
- `request_rerun`: still allowed as a governance signal.

To clear staleness:

1. Rerun the simulation.
2. Regenerate the markdown report.
3. Regenerate the governance packet.
4. Review the newly revision-bound packet.

## Governance Remediation Planner Alpha

When a governance packet is `action_required`, the backend can generate a
revision-bound remediation plan:

```text
GET  /api/business-simulation/:simulation_id/governance-remediation-plan
POST /api/business-simulation/:simulation_id/governance-remediation-plan
```

Generated file:

```text
governance_remediation_plan.json
```

The plan is advisory. It does not mutate scenario inputs, fund terms, ledger, or
review status. Any scenario-changing option must still be copied into the
explicit scenario patch commit flow.

Reserve shortfall options currently include:

- `reduce_distribution_to_restore_reserve`: scenario patch reducing planned distribution by the reserve shortfall.
- `capital_call_top_up_for_reserve`: scenario patch increasing called capital by the reserve shortfall.
- `lpac_reserve_waiver`: review action option that records a waiver without changing executable state.

High-risk branch packets can also include a governance action option for the
highest-risk branch response.

The remediation plan is bound to the packet revision. If the packet is stale,
the plan is generated with:

- `status`: `blocked_stale_packet`
- `adoption_allowed`: `false`

Regenerate the packet after rerun to produce a remediation plan that is
`ready_for_review`.

## Remediation Option Adoption Alpha

Scenario-patch remediation options can be routed back into the explicit
preview/commit workflow:

```text
POST /api/business-simulation/:simulation_id/governance-remediation-plan/options/:option_id/preview
POST /api/business-simulation/:simulation_id/governance-remediation-plan/options/:option_id/commit
```

Only options with `option_type: scenario_patch` can be previewed or committed.
The backend blocks adoption when the remediation plan was generated from an
older scenario revision.

Commit behavior:

- Writes the adopted option into `scenario_patch.json`.
- Updates `scenario.yaml` and/or `fund_terms.yaml` through the same scenario patch machinery.
- Appends a `remediation_option_commit` entry to `scenario_revisions.json`.
- Sets run state `pending_change` to `remediation_option_committed`.
- Requires rerun/report/packet regeneration before a fresh governance review.

The UI exposes this as `Preview Recommended` and `Commit Recommended & Rerun`
inside the `Remediation Plan` panel.

## Roadmap Revalidation Gate

Before starting each next formal roadmap milestone, rerun this gate:

1. Confirm the milestone still serves the MiroFish-first OASIS replacement goal.
2. Confirm the current order still protects the proposal/commit boundary.
3. Confirm ledger-affecting changes still require deterministic validation.
4. Decide whether the work is a formal roadmap milestone or a hardening sub-task.
5. If the user is in active LP discussions, prioritize LP-facing capital strategy,
   capital entry, governance readiness, and resource preparation views.

The current formal roadmap position is Milestone 3, not a new milestone name:

```text
Milestone 3: Multi-Round Fund Lifecycle Simulation
```

## Multi-Round Fund Lifecycle Alpha

The engine now emits an LP-facing lifecycle layer in `report_context.json` and
`state_snapshot.json`:

- `fund_lifecycle_summary`
- `capital_call_schedule`
- `nav_snapshots`
- `lp_readiness_summary`

The lifecycle alpha expands the 12-month run from a single executable capital
call into a multi-round fund operation:

1. Round 1 initial capital call funds the first investment.
2. Quarterly reporting records NAV snapshots.
3. Follow-on reserve review estimates next-round resource needs.
4. Liquidity and distribution still run through the waterfall and reserve review.
5. Round 2 follow-on reserve top-up capital call is issued after distribution,
   so it does not erase pre-distribution governance findings.
6. Unfunded commitment, paid-in capital, NAV, and paid-in multiple are reported
   for LP discussion.

The UI exposes this through:

- `LP Capital Lifecycle`
- `LP Readiness`
- `NAV Snapshots`

Acceptance checks:

- `cashflow_summary.capital_call_rounds` is at least `2`.
- `capital_call_schedule` includes a paid `initial` call and a paid `follow_on`
  call.
- `fund_lifecycle_summary.commitment_summary.unfunded_commitment` tracks
  remaining callable capital.
- `nav_snapshots` includes payment, investment, quarterly, liquidity,
  distribution, and follow-on payment moments.
- `lp_readiness_summary` identifies subscription, wiring, follow-on reserve,
  and LP reporting readiness.

## Document Evidence Binding Alpha

Milestone 4 adds a shared evidence registry:

```text
evidence_bindings.json
```

The same registry is embedded into:

- `report_context.json` as `evidence_bindings`.
- `business_report.md` under `Evidence Bindings`.
- `governance_packet.json` as prioritized `evidence_bindings.key_bindings`.
- The UI `Evidence Bindings` panel.

Binding policy:

```text
evidence_only_does_not_mutate_ledger
```

Each binding contains:

- `target_path`: the report, lifecycle, branch, term, or proposal field being
  supported.
- `target_type`: financial proposal, fund-term proposal, executable term,
  LP lifecycle, capital call, NAV snapshot, branch risk, or report artifact.
- `source_ref`: source file/path such as `fund_terms.yaml`, `event_log.jsonl`,
  `ledger.jsonl`, `branch_results.json`, or source project hints.
- `source_snippet`: short human-readable supporting text.
- `confidence`: high/medium/low/unknown.
- `audit_trail`: how the field moved from source text or deterministic runtime
  into the report surface.

Acceptance checks:

- `evidence_bindings.json` is written after a run.
- `report_context.json.evidence_bindings.bindings_count` is populated.
- Proposed financial plan and proposed fund terms include source-text bindings
  but remain non-authoritative until explicit commit.
- LP lifecycle fields, follow-on reserve, capital calls, and NAV snapshots bind
  to runtime logs/state.
- Branch risks bind to `branch_results.json` and triggered fund terms.
- Governance packets prioritize LP lifecycle / capital strategy evidence before
  lower-priority proposal evidence.

Example committed term extraction test fixture:

- Annual management fee: `2.5%`.
- IC approval threshold: `75%`.
- Preferred return: `9%`.
- GP carry: `25%`.
- Default interest: `13%`.
- Cure period: `20` days.
- Reserve minimum: `300,000`.
- Audit materiality: `150,000`.

## LPAC / IC Meeting Pack Export Alpha

Milestone 5 packages existing simulation, governance, and evidence outputs into
LP-facing meeting materials. This is an export-only layer:

```text
POST /api/business-simulation/:simulation_id/meeting-pack
```

Generated files:

```text
meeting_pack.json
meeting_pack.md
meeting_pack.docx
meeting_pack.pdf
```

The JSON and Markdown files are available through the output browser. DOCX and
PDF are generated as delivery files and returned by path/byte metadata from the
export endpoint.

The pack includes:

- Meeting agenda for LP / LPAC / IC / GP / auditor review.
- LP capital brief covering capital called, paid-in capital, unfunded
  commitment, capital call rounds, NAV, follow-on reserve, reserve shortfall,
  and LP readiness next step.
- Decision table sourced from `governance_packet.json`.
- Risk appendix sourced from branch risk and branch action outputs.
- Evidence appendix sourced from prioritized document evidence bindings.
- Source file index for audit follow-up.

Generation policy:

```text
export_only_does_not_mutate_ledger_or_review_state
```

Meeting pack generation can create a missing governance packet from the current
`report_context.json`, but it does not approve, waive, rerun, commit extracted
terms, or mutate ledger state. If a packet is stale, the pack carries that stale
status into `packet_status` rather than hiding it.

Acceptance checks:

- `meeting_pack.json` and `meeting_pack.md` can be read from
  `/outputs/:filename`.
- `meeting_pack.docx` is a valid DOCX zip containing `word/document.xml`.
- `meeting_pack.pdf` is written as a portable PDF snapshot.
- The pack includes agenda, decision table, risk appendix, evidence appendix,
  LP readiness, capital call lifecycle, and proposal commit-policy fields.

## Portfolio Scenario Expansion Alpha

Milestone 6 expands `branch_results.json` from a small governance comparison set
into a richer portfolio scenario library for LP / LPAC / IC discussion.

Generation policy:

```text
branch_comparison_only_does_not_mutate_base_ledger
```

Expanded branch coverage:

- `down_round`: valuation impairment, follow-on reserve pressure, LP valuation
  update.
- `bridge_financing`: bridge amount, runway extension, conversion discount, dry
  powder tradeoff.
- `write_off`: full NAV impairment, IC write-off decision, LP material loss
  notice, audit evidence.
- `delayed_exit`: delayed distribution timing and quarterly NAV/reporting
  update.
- `partial_exit`: partial waterfall preview and residual position review.
- `regulatory_block`: deployment block, compliance escalation, LP risk update.
- `lp_default_cure_or_waiver`: cure payment or LPAC waiver after default notice.

The branch library is surfaced through:

- `branch_results.json.scenario_expansion`.
- `report_context.json.portfolio_scenario_expansion`.
- `business_report.md` under `Portfolio Scenario Expansion`.
- `governance_packet.json.branch_risk_summary` and `branch_actions`.
- `meeting_pack.json.scenario_expansion` and the meeting pack risk appendix.
- `evidence_bindings.json` as branch-risk evidence bindings.

Acceptance checks:

- `branch_results.json.scenario_expansion.branch_count` is `12`.
- Each M6 branch is present under `branch_results.json.branches`.
- Risk scoring includes NAV impairment, down-round valuation, bridge financing,
  delayed exits, regulatory blocks, write-off state, and cure/waiver status.
- Meeting pack output includes scenario coverage so LP-facing materials explain
  the downside/upside scenario library, not only the base case.

## GitHub / Public Version Readiness Alpha

Milestone 7 packages the fund-governance module for public-alpha use without
promoting it to production fund administration software.

Tracked public assets:

- `docs/business-governance-public-alpha.md`
- `docs/examples/README.md`
- `examples/business-governance/demo_business/`
- `scripts/business_governance_public_alpha_smoke.py`

Root scripts:

```bash
npm run business:smoke
npm run business:example
npm run business:quickstart
```

Private beta access management:

```env
BUSINESS_DEMO_ACCESS_CODE=your_private_beta_code
VITE_BUSINESS_DEMO_PASSWORD=your_private_beta_code
BUSINESS_DEMO_OWNER_CODE=your_owner_console_code
BUSINESS_DEMO_ACCESS_REGISTRY_PATH=private/business-demo-access-codes.json
```

The access-code mechanism lives in the repo, but real access codes should stay
outside git in `.env`, `.env.local`, or deployment environment variables.
`BUSINESS_DEMO_ACCESS_CODE` protects the business-simulation backend API.
`VITE_BUSINESS_DEMO_PASSWORD` enables the frontend access prompt. When using
`npm run dev:stable`, the launcher can pass `BUSINESS_DEMO_ACCESS_CODE` from the
root `.env` into the frontend dev server.

For multi-group private beta use, set `BUSINESS_DEMO_OWNER_CODE` and open:

```txt
http://127.0.0.1:5174/admin/access-codes
```

The owner console writes a gitignored registry at
`private/business-demo-access-codes.json` by default. Registry entries store
hashed codes, group labels, scopes, expiry dates, enable / disable status, and
audit events. Plaintext trial codes are shown only once at creation time.

This is an invitation-only beta gate, not a replacement for full server-side user
accounts on a public internet deployment with sensitive data.

`business:smoke` runs the synthetic demo through:

1. Fund-governance simulation run.
2. Markdown report generation.
3. Governance packet generation.
4. LPAC / IC meeting pack generation.
5. Branch expansion validation.
6. Evidence binding policy validation.
7. DOCX and PDF meeting-pack validation.

Public boundary:

- Runtime outputs under `backend/uploads/` remain ignored.
- The tracked demo seed is synthetic and generic.
- Generated public examples should be compact summaries, not private uploaded
  documents or full client meeting packs.
- AGPL-3.0 remains the repository license; public deployment obligations should
  be reviewed before hosting a modified service.

Acceptance checks:

- A clean clone can run `npm run setup:all && npm run business:smoke`.
- `npm run business:example` writes
  `docs/examples/business-governance-alpha-summary.json`.
- README links to the fund-governance public-alpha docs and demo seed.
- The public-alpha docs explain install, outputs, governance boundaries, and
  license note.
