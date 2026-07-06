# MiroFish Business Governance Public Alpha

This document describes the private-beta Fund Governance Edition. This edition
is based on the MiroFish architecture, but it should be treated as a separate
repo / product line from the original MiroFish / Miracle mainline.

The module adds a MiroFish-native business / fund-governance simulation engine.
It can complement or replace the OASIS social-simulation slot for workflows
where the world being simulated is a fund operating process rather than a social
media population.

## Repository Identity

- Repo role: `MiroFish Fund Governance Edition`.
- Intended distribution: private GitHub repo / invitation-only beta.
- Upstream relationship: built on MiroFish architecture, not a replacement for
  the original upstream product identity.
- Audience: project owner, selected fund managers, LP-facing reviewers,
  IC / LPAC workflow reviewers, and technical private-beta testers.
- Boundary: no real LP confidential data, fund documents, legal advice,
  accounting records, or real access codes should be committed.

## Status

Public alpha. The module is ready for local demo, GitHub review, and controlled
external testing. It is not production fund administration software, and it is
not legal, tax, accounting, or investment advice.

## LP-Facing Trial Materials

Use the LP-facing material pack when inviting reviewers or running private-beta
walkthroughs:

- [LP-Facing Material Pack](./lp-facing/README.md)
- [One-Page Overview](./lp-facing/one-page-overview.md)
- [Demo Meeting Script](./lp-facing/demo-meeting-script.md)
- [Trial Feedback Form](./lp-facing/trial-feedback-form.md)
- [Outreach Email Templates](./lp-facing/outreach-email-templates.md)

## What It Simulates

The demo seed models a synthetic fund lifecycle:

- LP subscription and capital call.
- LP payment and unfunded commitment.
- IC approval and investment execution.
- Follow-on reserve review and capital call.
- NAV snapshots.
- Liquidity event, waterfall, distribution, and audit review.
- LPAC / IC governance packet and meeting pack.
- Portfolio scenarios: down round, bridge financing, write-off, delayed exit,
  partial exit, regulatory block, and LP default cure / waiver.

## Clean Install

```bash
npm run setup:all
npm run business:smoke
```

The smoke command uses a tracked synthetic demo seed from:

```text
examples/business-governance/demo_business/
```

If the runtime demo is missing, it copies the seed into:

```text
backend/uploads/simulations/demo_business/
```

Runtime files under `backend/uploads/` are ignored by git.

## Generate Example Output Summary

```bash
npm run business:example
```

This writes:

```text
docs/examples/business-governance-alpha-summary.json
```

The summary is intentionally compact and public-safe. Full runtime outputs remain
under `backend/uploads/simulations/<simulation_id>/business/`.

## Local UI

```bash
npm run dev:stable start
```

Then open:

```text
http://127.0.0.1:5174/business-simulation/demo_business
```

If ports are already occupied by older dev processes, stop or restart them before
using the UI. The smoke command does not require a browser or open network port.

## Private Beta Access Management

For a simple single-code alpha gate, set:

```env
BUSINESS_DEMO_ACCESS_CODE=your_private_beta_code
VITE_BUSINESS_DEMO_PASSWORD=your_private_beta_code
```

For grouped private beta trials, use the owner-only access console:

```env
BUSINESS_DEMO_OWNER_CODE=your_owner_console_code
BUSINESS_DEMO_ACCESS_REGISTRY_PATH=private/business-demo-access-codes.json
```

Then open:

```txt
http://127.0.0.1:5174/admin/access-codes
```

The owner console can create LP / fund-manager / IC reviewer trial groups with
labels, scopes, expiry dates, enable / disable status, and an audit log. The
registry stores PBKDF2 hashes only. Plaintext codes are displayed once when they
are created.

Do not commit real access codes to the repository. Put owner codes and trial
codes in `.env`, `.env.local`, deployment environment variables, or the
gitignored `private/` registry. `BUSINESS_DEMO_ACCESS_CODE` remains a
backward-compatible fallback. The registry is preferred for multi-group trials.

When using `npm run dev:stable`, setting only `BUSINESS_DEMO_ACCESS_CODE` in the
root `.env` is enough for local beta use; the stable launcher passes the value to
the frontend dev server. For static frontend builds or cloud deployments, set
both values explicitly.

This gate is intended for invitation-only beta distribution. It is not a
substitute for server-side authentication if you deploy a public internet
service with sensitive data.

## Main Outputs

Generated business outputs include:

- `compiled_world.json`
- `event_log.jsonl`
- `ledger.jsonl`
- `decision_records.jsonl`
- `rule_execution_records.jsonl`
- `branch_results.json`
- `state_snapshot.json`
- `report_context.json`
- `business_report.md`
- `governance_packet.json`
- `governance_memo.md`
- `governance_review.json`
- `governance_remediation_plan.json`
- `evidence_bindings.json`
- `meeting_pack.json`
- `meeting_pack.md`
- `meeting_pack.docx`
- `meeting_pack.pdf`

## Governance Boundaries

The alpha deliberately separates proposed values from authoritative simulation
state:

- Extracted financial hints are proposal-only until explicitly committed.
- Extracted fund terms are proposal-only until explicitly committed.
- Scenario patch preview does not mutate executable inputs.
- Governance packets and meeting packs package evidence; they do not approve,
  waive, rerun, or mutate the ledger.
- Portfolio scenario branches are comparison outputs only:
  `branch_comparison_only_does_not_mutate_base_ledger`.

## Public Readiness Checklist

Before publishing a public branch or release, verify:

- `npm run business:smoke` passes.
- `npm run build` passes.
- `backend/.venv/bin/python -m pytest backend/tests/test_business_simulation.py -q`
  passes.
- No private uploaded files are staged from `backend/uploads/`.
- Any generated meeting pack shared publicly uses synthetic or approved data.
- The repository license and third-party dependency notices remain visible.

## License Note

The repository is currently licensed under AGPL-3.0. Public deployments or
network services based on modified versions should be reviewed against AGPL-3.0
source-availability obligations. This note is informational and not legal advice.
