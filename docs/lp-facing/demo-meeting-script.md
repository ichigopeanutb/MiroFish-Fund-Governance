# Demo Meeting Script

Suggested length: 30 minutes.

Audience: LP, fund manager, IC / LPAC reviewer, or technical private-beta
tester.

## Before The Meeting

Send:

- [One-Page Overview](./one-page-overview.md)
- Trial access code if the reviewer will run the local demo.
- Reminder: synthetic demo only; no real LP or fund data.

Prepare:

- Local demo page:

```text
http://127.0.0.1:5174/business-simulation/demo_business
```

- Owner console, if assigning trial access:

```text
http://127.0.0.1:5174/admin/access-codes
```

## Meeting Agenda

### 0-5 Minutes: Context

Suggested language:

> This is a private beta of MiroFish Fund Governance Edition. It is not fund
> administration software and not investment, legal, tax, or accounting advice.
> The purpose today is to test whether the workflow helps us rehearse fund
> operations, governance decisions, and LP-facing materials before using real
> data.

Clarify the review role:

- LP reviewer: focus on capital, reporting, transparency, and evidence.
- Fund manager / GP reviewer: focus on workflow, operational realism, and
  preparation burden.
- IC / LPAC reviewer: focus on decision packet, risk, evidence, and meeting
  readiness.
- Technical tester: focus on setup, access flow, repeatability, and outputs.

### 5-12 Minutes: Run The Simulation

Actions:

1. Open `business-simulation/demo_business`.
2. Click `Run Fund Simulation`.
3. Point to the top metrics:
   - Capital called
   - Capital paid
   - Unfunded commitment
   - NAV
   - Distributions
   - Ledger status
4. Walk through the timeline.

Questions to ask:

- Does this sequence resemble a real fund operating cycle?
- Which steps feel too simplified?
- Which missing step would matter most before showing this to another LP or IC
  reviewer?

### 12-18 Minutes: Governance And Evidence

Actions:

1. Click `Generate Report`.
2. Click `Generate Packet`.
3. Show:
   - Governance packet
   - Branch risk summary
   - Evidence bindings
   - Human review / approval status

Questions to ask:

- Would this help prepare an IC or LPAC discussion?
- Which evidence references are useful?
- Where would a reviewer ask for more source support?

### 18-24 Minutes: Meeting Pack

Actions:

1. Click `Generate Meeting Pack`.
2. Show:
   - Agenda
   - Decision table
   - Risk appendix
   - Evidence appendix
   - DOCX / PDF availability if generated

Questions to ask:

- Would this meeting pack save preparation time?
- Is the decision table clear enough?
- What would need to change before this feels boardroom-ready?

### 24-28 Minutes: Trial Fit

Ask the reviewer to choose one primary value:

- LP communication tool
- IC / LPAC preparation tool
- Fund operation simulation tool
- Audit / evidence review tool
- Portfolio scenario planner
- Not yet useful

### 28-30 Minutes: Next Step

Suggested close:

> The next version will be shaped by reviewer feedback, especially around LP
> capital readiness, fund terms, waterfall realism, governance decisions, and
> meeting-pack usefulness. I will send a short feedback form so we can turn this
> into the next build milestone.

## What Not To Say

- Do not say it predicts fund performance.
- Do not say it replaces legal counsel, auditors, fund administrators, or
  investment committees.
- Do not imply real LP data can be uploaded during alpha.
- Do not promise production authentication or compliance features until those
  are actually built.
