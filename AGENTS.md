# MiroFish Fund Governance Edition - Agent Operating Contract

## Objective

Build a MiroFish-native system of rehearsal for fund operations. The product
must let GP, LP, IC, LPAC, finance, and operations teams test fund terms,
capital strategy, governance decisions, and portfolio scenarios before any
real-world decision or movement of money takes effect.

This repository is not a fund administrator, accounting book, bank, custodian,
KYC / AML provider, legal adviser, tax adviser, or investment adviser.

## First-Principles Invariants

These invariants are more important than any individual feature:

1. Facts, proposals, and committed simulation state are separate data classes.
2. LLMs and extracted text may propose; deterministic validators and authorized
   human review commit simulation state.
3. No proposal, report, evidence binding, or meeting-pack export may directly
   mutate the ledger.
4. Every committed state transition must identify its command, event, affected
   objects, rule version, authority, evidence, and prior state.
5. Money must have currency and an explicit precision / rounding policy.
6. Ledger entries must balance, and repeated commands must not post twice.
7. The same versioned inputs and seed must reproduce the same normalized result.
8. Governance decisions must be tied to a specific packet and rule revision.
9. Real LP, fund, banking, tax, identity, or confidential document data must not
   enter tracked fixtures, logs, screenshots, or examples.
10. A simulation result is not proof of legal, accounting, tax, or investment
    correctness.

## Current Milestone

The active milestone is `Formal Phase 0 - Freeze and Characterize`.

Do not create the formal-v1 branch, add production infrastructure, or perform a
broad domain refactor until the Phase 0 exit gate in
`FORMAL_EDITION_HARNESS.md` passes.

## Protected Harness Surfaces

Do not modify these during an implementation experiment unless the maintainer
explicitly changes the harness or evaluation standard:

- `AGENTS.md`
- `FORMAL_EDITION_HARNESS.md`
- `scripts/formal_eval.sh`
- `formal_harness/results.tsv`
- `formal_harness/golden/`
- `formal_harness/contracts/`
- `backend/tests/`
- tracked demo inputs under `examples/business-governance/`

An implementation change must not weaken, delete, skip, or rewrite a failing
check. A harness change is its own reviewed milestone and must be evaluated
against the previous harness.

## Editable Surfaces

During Formal Phase 0, edits should normally stay within:

- characterization and replay code under
  `backend/app/services/business_simulation/`
- API contract extraction helpers under `backend/app/api/`
- additional non-protected documentation under `docs/`
- Phase 0 scripts that do not replace the fixed evaluator
- new characterization fixtures that have been explicitly reviewed before they
  become protected golden inputs

Preserve unrelated working-tree changes. Never stage or revert files outside
the current hypothesis.

## Required Workflow

1. Read `FORMAL_EDITION_HARNESS.md` and the latest results / failure record.
2. Re-run the roadmap fit check against the current LP and business objective.
3. Inspect `git status` and preserve all unrelated changes.
4. State one narrow, measurable hypothesis.
5. Run the fixed evaluator before the change when a clean comparison is needed.
6. Modify the smallest necessary surface.
7. Run `bash scripts/formal_eval.sh`.
8. Use a separate verification pass for financial, governance, migration, auth,
   or data-boundary changes.
9. Record the result in `formal_harness/results.tsv`; preserve failure logs.
10. Keep the change only when the evidence is clear and no invariant regresses.

## Fixed Evaluation Command

```bash
bash scripts/formal_eval.sh
```

The evaluator stores run logs under `.formal_harness/runs/`. Those logs are
local and gitignored so they can capture failures without publishing sensitive
machine paths or environment details.

## Human Gates

Explicit maintainer approval is required before:

- changing a protected harness surface or acceptance threshold;
- adding or replacing a financial golden case;
- introducing real or identifiable LP / fund data;
- changing authentication, tenant isolation, secrets, deployment, billing,
  payments, banking, KYC / AML, or production data retention;
- running a destructive database migration or publishing a release;
- declaring a legally or financially material rule correct without a qualified
  domain reviewer or an accepted oracle.

Routine source changes, local tests, characterization, documentation, and
reversible refactors inside the active milestone do not need repeated approval.

## Stop Conditions

Stop and escalate only when:

- the same blocking failure remains after three materially different attempts;
- progress requires changing a protected evaluator or permission boundary;
- the next step requires real confidential data or an external production
  action;
- financial or legal correctness cannot be determined without a new oracle;
- the requested work would violate a first-principles invariant.

Do not stop merely because work is long, difficult, or requires several local
iterations.
