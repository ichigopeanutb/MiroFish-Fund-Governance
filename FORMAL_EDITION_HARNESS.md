# Formal Edition Harness

This is the planning and execution contract for turning the current MiroFish
Fund Governance Edition alpha into a formal-version foundation.

It applies Lilian Weng's harness framing locally: the harness includes the
objective, workflow, context, tools, persistent artifacts, permissions,
evaluation, failure memory, and human gates around the coding loop.

## 1. North-Star Outcome

A fund team can rehearse an LP-to-distribution lifecycle and answer:

- What assumptions and governing terms are in force?
- What capital is committed, called, paid, unfunded, reserved, invested, and
  distributable at each point in simulated time?
- Who has authority to approve, reject, waive, recuse, or require a rerun?
- Which rules and evidence caused each state transition?
- How would alternative decisions change liquidity, NAV, governance risk,
  obligations, and LP communication?
- Can the result be replayed, reconciled, reviewed, and exported without being
  mistaken for a real-world posting?

## 2. Formal Phase 0 Objective

Freeze and characterize the current MVP before formal-v1 development.

Phase 0 does not make the alpha production-ready. It creates a trustworthy
branch point by making existing behavior visible, reproducible, and bounded.

## 3. Phase 0 Inputs

- Current commit and full working-tree inventory.
- Tracked synthetic demo inputs under `examples/business-governance/`.
- Existing business simulation tests and public-alpha smoke workflow.
- Current API routes, editable fields, outputs, schema versions, and reports.
- Formal-edition benchmark and readiness plan under `docs/`.

## 4. Phase 0 Workstreams

### A. Contract Inventory

Produce machine-readable and human-readable inventories for:

- API routes and methods;
- commands and state transitions;
- input files and editable term fields;
- event, decision, rule, ledger, report, packet, and export schemas;
- proposal-only and non-mutation policies;
- current single-party and file-storage assumptions.

### B. Reproducibility Baseline

- Normalize volatile values such as timestamps and local paths.
- Run the same tracked seed twice.
- Compare normalized events, ledger, decisions, rules, branch results, and
  report context.
- Record every nondeterministic field instead of hiding it.

### C. Replay Characterization

- Determine whether the current event and ledger logs can reconstruct the final
  state.
- Add characterization tests for missing, duplicate, reordered, and partially
  written events.
- Record current failures as product evidence; do not redesign the event store
  inside the same experiment.

### D. Financial Golden Cases

Create reviewable synthetic cases for:

- commitment, call, payment, and unfunded reconciliation;
- management fee basis and period;
- LP default and cure;
- IC rejection with no investment posting;
- reserve check;
- return of capital, preferred return, carry, and LP distribution.

The first Phase 0 pass may label a case `unverified`. A case becomes a protected
golden oracle only after its inputs, formulas, expected outputs, currency, and
rounding rule are reviewed.

### E. Data and Permission Boundary

Document:

- synthetic demo, confidential pilot, and production data classes;
- who may view, propose, review, approve, export, and administer;
- which actions can change simulation state;
- which integrations remain external systems of record;
- retention, deletion, masking, backup, and audit-export requirements.

### F. Architecture Decisions

Prepare ADRs for:

- Money / Currency / FX;
- Event Store / Snapshot / Replay;
- Command Idempotency;
- Rule and Schema Versioning;
- Workflow and Human Approval;
- Authentication / Organization / Fund Scope;
- Document Evidence and Confidentiality;
- Simulation-to-System-of-Record Integration.

Phase 0 records decisions and alternatives. It does not need to implement every
selected production component.

## 5. Fixed Evaluation

Run:

```bash
bash scripts/formal_eval.sh
```

The current fixed evaluator checks:

1. repository whitespace / patch integrity;
2. backend business simulation tests;
3. complete public-alpha smoke workflow;
4. production frontend build.

Phase 0 will add characterization evidence around this evaluator, not silently
replace its existing checks.

## 6. Persistent Harness Artifacts

- `AGENTS.md`: invariants, permissions, protected surfaces, and stop rules.
- `FORMAL_EDITION_HARNESS.md`: objective, plan, workstreams, and gates.
- `scripts/formal_eval.sh`: fixed local evaluator.
- `formal_harness/results.tsv`: append-only run summaries.
- `.formal_harness/runs/`: local detailed output and failure logs.
- `formal_harness/contracts/`: reviewed contract inventories.
- `formal_harness/golden/`: reviewed synthetic golden cases.

Chat history is not authoritative project state.

## 7. Evaluation Result Contract

The evaluator prints:

```text
EVAL_STATUS=pass|fail
EVAL_SCORE=0..100
EVAL_CHECKS_PASSED=<integer>
EVAL_CHECKS_FAILED=<integer>
EVAL_RUNTIME_SECONDS=<integer>
EVAL_RUN_DIR=<local path>
```

Every retained experiment adds one line to `formal_harness/results.tsv` with:

```text
timestamp, commit, status, score, passed, failed, runtime, milestone,
hypothesis, result, run_dir
```

## 8. Keep / Reject Rules

Keep a Phase 0 change when it:

- reveals or locks down current behavior without changing domain meaning;
- increases reproducibility, replay visibility, or contract coverage;
- preserves every first-principles invariant;
- passes the fixed evaluator;
- records newly discovered uncertainty instead of fabricating certainty.

Reject or split a change when it:

- mixes characterization with a broad redesign;
- edits the evaluator to accommodate the implementation;
- introduces real data or unreviewed financial claims;
- reduces auditability or makes an event harder to replay;
- changes financial behavior without a reviewed oracle;
- makes the alpha and formal-version boundaries less clear.

## 9. Phase 0 Exit Gate

All items are required before tagging and branching:

- Fixed evaluator passes from a known commit.
- Contract inventory covers every business simulation endpoint and output.
- Two-run normalized reproducibility result is recorded.
- Replay capability and gaps are demonstrated by tests.
- Core financial cases are protected golden, or explicitly accepted as
  unresolved blockers.
- Data classification, permission matrix, threat model, and non-advice boundary
  are documented.
- Architecture decisions required for Formal Milestone 1 are accepted.
- Unrelated working-tree changes are resolved or excluded from the branch point.

Only then:

```text
tag fund-governance-mvp-v0.1.0
branch fund-governance-formal-v1
```

## 10. Post-Phase-0 Order

1. Domain Core and Replay v1.
2. LP Capital Readiness Workspace v1.
3. Governance Workflow and Segregation of Duties v1.
4. Multi-Round Lifecycle and Portfolio Scenarios v1.
5. Evidence and Reporting Interoperability v1.
6. Hosted Private Pilot v1.
7. Production Candidate and Public Packaging.

Before each milestone, rerun a roadmap fit check against real LP conversations,
capital-entry needs, operating resources, reviewer friction, and new evidence.
