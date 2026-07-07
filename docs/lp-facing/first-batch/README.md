# First Batch Private Beta Operations

This folder defines the first controlled reviewer batch for MiroFish Fund
Governance Edition. The goal is to validate whether invited reviewers understand
the product, trust the workflow boundary, and can identify the next high-value
milestone.

Do not add real reviewer names, email addresses, access codes, LP documents, or
fund materials to this folder. Filled trackers should live under `private/`.

## Roadmap Fit Check

This milestone is correct after the LP-facing material pack because the next
bottleneck is no longer raw feature count. The bottleneck is controlled learning
from real LP / fund-manager conversations.

The first batch should answer four questions:

- Do LP-facing reviewers understand what the simulator is for?
- Which outputs create trust: fund terms, waterfall, governance packet,
  evidence trail, meeting pack, or capital-readiness framing?
- What prevents a nontechnical reviewer from giving useful feedback?
- Which next build milestone should come first after the beta batch?

## Recommended Batch Size

Start with 5 to 10 reviewers. Keep the batch small enough to brief personally
and large enough to expose role differences.

Recommended mix:

- 2 LP / capital allocator reviewers.
- 2 fund manager / GP reviewers.
- 1 IC / LPAC reviewer.
- 1 fund operations / finance reviewer.
- 1 technical operator who can test the repo setup.
- 1 senior nontechnical advisor, if available.

## Reviewer Types

LP / capital allocator:

- Focus: whether the output helps them understand fund discipline, reporting,
  governance quality, and risk transparency.
- Best material: one-page overview, report screenshots, meeting-pack sample,
  and a 30-minute walkthrough.

Fund manager / GP:

- Focus: whether the simulator helps prepare for LP conversations, capital
  calls, governance review, and portfolio scenario planning.
- Best material: demo walkthrough, governance packet, terms / waterfall output,
  and follow-up feedback form.

IC / LPAC reviewer:

- Focus: whether decisions, waivers, approvals, evidence, and risk flags are
  organized in a reviewable way.
- Best material: governance packet and decision table.

Operations / finance reviewer:

- Focus: whether fund terms, capital call logic, waterfall, unfunded
  commitment, and ledger boundaries are credible.
- Best material: fund terms / waterfall output and scenario notes.

Technical operator:

- Focus: whether a repo-based setup works and whether the access-code mechanism
  is clear.
- Best material: private GitHub repo, README, runbook, and `.env.example`.

Senior nontechnical advisor:

- Focus: whether the product story is understandable and worth continued
  development.
- Best material: one-page overview, screenshots, final report sample, and three
  focused questions.

## Safe Material Flow

Before the walkthrough:

- Send the one-page overview.
- Send a short reviewer-specific message.
- Send screenshots or sample outputs only if they contain synthetic data.
- Do not send GitHub to nontechnical reviewers unless they specifically want to
  inspect the repo.

During the walkthrough:

- Run only synthetic demo data.
- Explain that this is a fund-governance simulation layer, not legal, tax,
  accounting, investment, or performance advice.
- Ask the reviewer to stay in one role for feedback.
- Capture the most confusing moment and the most valuable output.

After the walkthrough:

- Send the feedback form.
- Record feedback in a private tracker.
- Do not paste confidential relationship notes into the repo.
- Convert feedback into a synthesis after at least five completed reviews.

## Three-Week Operating Plan

Week 0: prepare materials.

- Confirm the demo page works locally.
- Prepare one synthetic report or screenshot pack.
- Create a private copy of the reviewer tracker.
- Decide which reviewer type each person represents.

Week 1: outreach.

- Invite 5 to 10 reviewers.
- Use different messages for LP, GP, IC / LPAC, technical, and senior advisor
  reviewers.
- Keep the ask simple: review the concept, not the codebase.

Week 2: walkthroughs.

- Run 30-minute sessions.
- Keep each session role-specific.
- Capture feedback immediately.

Week 3: synthesis.

- Aggregate the signal.
- Decide the next milestone.
- Do not expand access until the decision gate is reviewed.

## Exit Criteria

The first batch is complete when:

- At least 5 reviews are completed.
- At least 3 reviewer roles are represented.
- The top 3 valuable outputs are clear.
- The top 3 missing features or trust gaps are clear.
- Setup friction is separated from product-value feedback.
- The next milestone is chosen from evidence, not instinct alone.

## Decision Gate

Choose the next milestone using the feedback synthesis:

- LP / Fundraise Workspace: choose this if reviewers focus on capital
  readiness, LP communication, investor Q&A, and fundraising material quality.
- Hosted Demo / Access Flow: choose this if reviewers like the concept but setup
  friction blocks useful feedback.
- Meeting Pack Export: choose this if the governance packet and meeting
  materials are the strongest value signal.
- Editable Terms / Scenario Workspace: choose this if reviewers need to adjust
  assumptions before trusting the simulation.
- Multi-Round Lifecycle Simulation: choose this if reviewers say the core gap is
  realism across capital calls, NAV, follow-ons, exits, and distributions.
