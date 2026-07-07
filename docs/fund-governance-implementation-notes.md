# MiroFish Fund Governance Edition - Implementation Notes

This file tracks product-boundary decisions for the fund-governance edition.
It is a working implementation log, not a fund ledger and not an approval record.

## Roadmap Fit Check - Private Beta Access Management Alpha

Status: completed

This milestone is still aligned with the Fund Governance Edition roadmap because
the user is preparing LP / fund-manager contact and needs controlled trial access
before expanding the investment logic. The work should support private beta
distribution without confusing this edition with the original MiroFish / Miracle
mainline.

## Product Boundary

- This edition is `MiroFish Fund Governance Edition`.
- It is based on MiroFish architecture, but should be packaged as a separate
  private beta / repo line when shared externally.
- Do not push this work directly into the original MiroFish mainline as if it
  were the canonical product.
- Do not commit real access codes, LP data, fund documents, legal advice,
  accounting records, or investor-identifying information.

## Access Management Decisions

- Trial access is managed by project-owner-issued access codes.
- The repo contains the access management mechanism, not real codes.
- Real codes live in `.env`, `.env.local`, deployment secrets, or a gitignored
  local registry file.
- The alpha registry is file-backed at `private/business-demo-access-codes.json`
  by default.
- Registry entries store PBKDF2 hashes, not plaintext codes.
- Plaintext codes are displayed only once when an owner creates them.
- The owner console requires `BUSINESS_DEMO_OWNER_CODE` and is disabled when
  that value is not set.

## Non-Goals For This Milestone

- This is not production authentication.
- This does not replace GitHub private repo permissions.
- This does not implement user accounts, SSO, billing, or legal access control.
- This does not allow access code decisions to mutate simulation ledger state.

## Deviations

- The earlier single-code beta gate is kept as a backward-compatible fallback,
  but the preferred path is the multi-code registry.
- The frontend no longer relies only on `VITE_BUSINESS_DEMO_PASSWORD`; it asks
  the backend whether access is required and verifies codes server-side.

## Acceptance Checklist

- The backend rejects business-simulation API access when a registry or legacy
  beta code is configured and no valid code is provided.
- The backend accepts an active registry code without exposing plaintext codes
  in the registry file.
- The owner console can create, list, enable, disable, and audit trial groups.
- The frontend demo gate verifies codes with the backend.
- The owner console route is available at `/admin/access-codes`.
- `.env.example` documents the owner code and registry path without real values.

## Roadmap Fit Check - GitHub Separation / Repository Identity Alpha

Status: completed

After the Fund Governance Edition became usable for private beta trials, the
next bottleneck was not another simulation feature. The bottleneck was product
identity: external testers should not confuse this repo with the original
MiroFish / Miracle mainline.

## Repository Separation Decisions

- The private beta was pushed to a separate private GitHub repository:
  `ichigopeanutb/MiroFish-Fund-Governance`.
- The original `ichigopeanutb/MiroFish` `main` branch was not used as the
  distribution target for this edition.
- The local branch used for the first private-beta push was
  `fund-governance-edition-alpha`.
- The first pushed commit was `b1d3941 Add MiroFish Fund Governance Edition alpha`.
- The new repo README must identify the repo as `MiroFish Fund Governance
  Edition` in the first viewport before preserving upstream MiroFish context.

## Repository Identity Non-Goals

- Do not present this repo as the canonical upstream MiroFish product.
- Do not hide the upstream MiroFish architecture relationship.
- Do not distribute private beta access by committing real codes.
- Do not add real LP / fund data to make the demo feel more realistic.

## Roadmap Fit Check - LP-Facing Material Pack Alpha

Status: completed

After the MVP and private GitHub packaging were complete, the next bottleneck
became adoption: LPs, fund managers, IC / LPAC reviewers, and technical trial
users need different entry points into the beta. This milestone adds a
controlled LP-facing material pack so private-beta conversations can produce
actionable product feedback instead of broad reactions.

## LP-Facing Material Decisions

- Add `docs/lp-facing/` as the reviewer-facing material pack.
- Keep the materials synthetic-demo only.
- Position the product as a fund-governance rehearsal layer, not a performance
  forecast, investor portal, legal advisor, tax advisor, or accounting system.
- Provide separate material for first contact, demo walkthrough, feedback
  capture, and outreach by reviewer type.
- Use the feedback form to decide the next build milestone, especially around LP
  capital readiness, fund terms, waterfall realism, governance review, evidence
  binding, meeting-pack usefulness, and hosted/private beta distribution.

## Roadmap Fit Check - First Batch Private Beta Operations Alpha

Status: completed

This milestone is aligned with the current roadmap because the user is preparing
LP contact and needs a controlled first reviewer batch before opening the beta
more broadly. The work prioritizes LP-facing clarity, capital-readiness
feedback, and reviewer operations over deeper simulation complexity.

This also reinforces the operating rule that every next milestone should start
with a roadmap fit check. The roadmap should not be followed mechanically; it
should be re-evaluated against current evidence, especially LP conversations,
fundraising readiness, strategy preparation, and reviewer friction.

## First Batch Decisions

- Add `docs/lp-facing/first-batch/` as the operating pack for the first
  controlled private beta cohort.
- Target 5 to 10 reviewers instead of broad public access.
- Include LP / capital allocator, fund manager / GP, IC / LPAC, operations /
  finance, technical operator, and senior nontechnical advisor perspectives.
- Keep real reviewer names, emails, relationship notes, access codes, and
  confidential feedback outside git.
- Use `private/` for filled trackers and synthesis files that contain real
  relationship context.
- Treat nontechnical reviewers differently from technical repo testers: send
  result materials and focused questions, not setup instructions.
- Use first-batch feedback to choose the next milestone from LP / Fundraise
  Workspace, Hosted Demo / Access Flow, Meeting Pack Export, Editable Terms /
  Scenario Workspace, or Multi-Round Lifecycle Simulation.
