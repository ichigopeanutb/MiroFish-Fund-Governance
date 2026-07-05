# MiroFish Fund Governance Edition - Implementation Notes

This file tracks product-boundary decisions for the fund-governance edition.
It is a working implementation log, not a fund ledger and not an approval record.

## Roadmap Fit Check - Private Beta Access Management Alpha

Status: in progress

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
