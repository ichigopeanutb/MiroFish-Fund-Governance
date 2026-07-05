# Business Governance Demo Seed

This directory contains the tracked public-alpha seed for the MiroFish business
governance engine.

The smoke script copies `demo_business/` into:

```text
backend/uploads/simulations/demo_business/
```

when that runtime directory is missing. Runtime outputs remain ignored by git.

Seed files:

- `business/business_simulation_config.json`
- `business/fund_terms.yaml`
- `business/scenario.yaml`
- `business/agent_profiles.yaml`

The seed is intentionally generic and synthetic. It is suitable for public demo
and test usage, not legal, tax, accounting, or investment advice.
