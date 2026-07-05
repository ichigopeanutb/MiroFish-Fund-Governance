# Object-Centric Business / Investment Governance World Simulator for MiroFish

Last updated: 2026-06-30

This document is an MVP engineering specification for adding a new simulation backend to MiroFish. It does not replace MiroFish as a product. It replaces or complements the current OASIS social-media simulation slot with an object-centric business / investment governance world simulator.

Target pipeline:

```text
documents
-> ontology generation
-> Zep graph / memory layer
-> business / investment agent profiles
-> business-governance world simulator
-> object-centric event log + business event log
-> report agent
```

Non-goals for MVP:

- Do not build a generic chatbot.
- Do not let LLM output directly mutate world state.
- Do not attempt full PDF-to-contract-rule extraction on day one.
- Do not adopt Temporal / BPMN / DMN / Mesa / LangGraph as the runtime before the minimal world semantics are proven.

Core safety rule:

```text
LLM may propose. Deterministic validators commit.
```

## 1. Benchmark and First-Principles Analysis

### 1.1 Benchmark / Reference Systems

| Benchmark | What it solves | What it does not solve | Use for MiroFish |
|---|---|---|---|
| OASIS / CAMEL OASIS | Large-scale social-media-style agent simulation with dynamic networks, posts, comments, following, recommendations, and social phenomena such as information spreading and polarization. | It models social platforms, not contracts, obligations, fund ledgers, capital calls, voting thresholds, default remedies, or waterfall distributions. | Keep as the social world simulator. Use its MiroFish integration as the adapter pattern to replace. |
| Current MiroFish runner | Creates simulation directories, prepares profiles/config, starts Python subprocesses, monitors `actions.jsonl`, and exposes run state. | Assumes platforms are `twitter` / `reddit`, actions are platform social actions, profiles contain social persona fields, and reports are written as future social prediction reports. | Preserve the lifecycle and directory shape; abstract engine-specific preparation, run command, log parser, and report context. |
| Private equity / VC fund models | Model commitments, capital calls, investments, management fees, NAV, exits, distributions, carry, hurdle, and clawback. | Usually spreadsheet-centric and deterministic; weak on governance decision processes, clause provenance, multi-party behavior, and audit event replay. | Use as the business domain kernel and test oracle. |
| Capital call / distribution waterfall models | Capture exact cashflow mechanics and LP/GP economic consequences. | Do not model soft governance friction, IC deliberation, side-letter conflicts, regulatory delay, or scenario branching by themselves. | MVP must support these before any LLM agent is added. |
| ILPA templates | Provide industry-standard reporting references, including reporting, performance, capital call and distribution templates. | They are reporting formats, not a simulation runtime or legal rule engine. | Use as output alignment and acceptance tests for report context fields. |
| Portfolio management simulation | Tracks portfolio company performance, follow-on rounds, exits, markups, reserves, and risk. | Often under-specifies legal obligations, voting, side letters, and auditability. | Add after cashflow + decision records work. |
| Business process simulation | Models process steps, resources, queues, durations, exceptions, and throughput. | Classic process simulation often has a single case id and weak object-centric semantics. | Use for event queue and process state patterns. |
| OCEL / object-centric process mining | Provides an event log model where events can touch multiple objects, objects have types, and relationships can be qualified. OCEL 2.0 also supports object changes and object relationships. | It is a log/exchange standard, not a domain simulator, rule engine, or financial ledger. | Adopt OCEL-style event log shape immediately. Full OCEL 2.0 export can be a product milestone. |
| BPMN | Standard notation for business process diagrams and executable process semantics. | Too heavy for MVP and weak as a direct representation of contract economics. | Use later for importing/exporting process diagrams. Do not use as MVP runtime. |
| DMN / FEEL | Standardizes decision models, decision tables, expression language, and interchange. | Does not own long-lived simulation state, event queues, ledgers, or contract provenance. | Use later for explicit voting/default/compliance decision tables. MVP can define a simpler rule DSL. |
| Discrete-event simulation | Models state changes triggered by ordered events in simulated time. | Generic DES does not define fund terms, obligations, cashflow posting, or governance objects. | This is the MVP runtime shape. Use `heapq` first. |
| Agent-based simulation | Models agents with local policies interacting in a world. | Generic ABM can become opaque if agents mutate state without constraints. | Agents should emit intents; validators and rule engines commit state. |
| Computational law / legal contract automation | Encodes legal rules, obligations, deadlines, remedies, and compliance checks. | Contract language is ambiguous; full automation is high-risk without expert review. | Use structured YAML clauses first, with evidence refs back to documents. |
| Financial digital twin | Mirrors financial entities, state, and flows for scenario simulation. | Often enterprise-specific and may not model human governance decisions. | Product positioning: MiroFish becomes a graph-backed financial/governance digital twin generator. |
| SimPy | Python process-based DES with generator processes and shared resources. | Adds dependency and process semantics before MiroFish knows its fund-world minimal kernel. | Consider after MVP if resource queues and concurrent process models get complex. |
| Mesa | Python ABM framework with grids/schedulers, visualization, and data collection. | Its default mental model is agent-first, not contract/object/ledger-first. | Useful for research prototypes; not MVP runtime. |
| Temporal | Durable workflow platform for reliable long-running business processes. | Requires service/deployment complexity and is built for real workflow execution, not cheap scenario replay. | Product-stage option when simulations become durable asynchronous jobs. |
| LangGraph | Stateful long-running agent orchestration with persistence, streaming, and human-in-the-loop. | It orchestrates LLM agents; it is not a deterministic legal/financial simulator. | Use later as optional LLM decision sidecar, not as source of truth. |
| AutoGen / CrewAI | Multi-agent application frameworks. AutoGen Core offers event-driven multi-agent infrastructure; CrewAI offers agents, flows, guardrails, memory, and observability. | They optimize collaboration workflows, not auditable ledger/rule simulation. | Useful for soft advisory agents after rule kernel exists. |
| Concordia | Generative social simulation library using entities, components, engine, and a game-master pattern. | It is LLM-centered and social/generative; the GM can be too subjective for legal/financial commits. | Good design reference for separating actors, environment, and resolution; do not adopt directly for MVP. |
| PM4Py | Python process mining library supporting discovery, conformance, predictive mining, and object-centric process mining. | It analyzes event logs; it does not produce fund-governance simulation state. | Use after MVP for validating logs, discovering process variants, and visualizing bottlenecks. |

Public standards / datasets / examples useful for validation:

- ILPA templates hub: align report context and cashflow output naming with reporting, performance, capital call, distribution, and portfolio company metrics templates.
- OCEL 2.0 sample logs and JSON/SQLite/XML formats: validate whether our event log can be converted without losing object relationships.
- OMG BPMN examples: later export demo process diagrams for `FundClosing -> CapitalCall -> ICMeeting -> Distribution`.
- DMN decision tables: later encode voting thresholds, default status, and compliance gates.
- PM4Py examples: later run process discovery and conformance checks on the generated `event_log.jsonl`.
- Spreadsheet fund waterfalls: MVP test oracle for capital call, management fee, default penalty, and distribution math.

New capability compared with OASIS:

OASIS simulates what agents say and do on a social platform. The new engine simulates what legally, financially, and procedurally changes in a fund world. Its core output is not posts, comments, and likes; it is auditable changes to obligations, decisions, clauses, cashflows, ledgers, and object state.

Report contract compatibility:

The report agent needs a stable analysis context. Short term, emit both:

- `business/event_log.jsonl`: object-centric canonical log.
- `business/report_context.json`: report-ready summary that can be consumed without knowing every event schema.

Medium term, abstract report tools so OASIS reports use social prompts/tools and business-governance reports use governance prompts/tools.

### 1.2 First-Principles Analysis

If OASIS is a social-media world simulator, the business-governance world simulator's smallest meaningful world unit is not an agent and not a message. It is:

```text
object + legally/financially meaningful event + validated state transition
```

Minimum world units:

- `Entity`: a real-world party or object, such as Fund, LP, GP, SPV, PortfolioCompany, IC, Auditor, Regulator.
- `RoleBinding`: an entity's legally relevant role in a context, such as LP in Fund I, GP of Fund I, auditor of Fund I.
- `Contract` / `Clause`: source of rights, obligations, thresholds, remedies, and reporting duties.
- `Rule`: deterministic executable representation of a clause or policy.
- `Event`: a timestamped happening that touches one or more objects and may trigger rules.
- `StateTransition`: the committed change to state.
- `Cashflow` / `LedgerEntry`: economic result that must reconcile.
- `DecisionRecord`: who decided, under what authority, with what evidence and result.
- `RuleExecutionRecord`: which rule ran, inputs, outputs, and why it passed/failed.

Minimum real investment-governance units:

- Commitment: how much an LP has committed.
- Unfunded commitment: remaining callable amount.
- Capital call notice: amount, due date, notice date, purpose, affected LPs.
- Payment/default: whether a call was paid on time and default remedies.
- Investment authorization: IC / GP decision process and threshold.
- Portfolio holding: cost, ownership, valuation, status.
- Fees and expenses: management fee basis, offsets, periods.
- Distribution waterfall: return of capital, preferred return/hurdle, GP catch-up, carry.
- Reporting obligation: report type, cadence, recipient, deadline.
- Side-letter / veto / restriction: special rights and compliance gates.

State changes that materially alter legal, financial, or governance outcomes:

- Commitment signed or amended.
- Capital call issued, paid, late, waived, or defaulted.
- Voting threshold reached or missed.
- Veto right exercised or expired.
- Investment approved, rejected, delayed, funded, or unwound.
- Clause obligation created, fulfilled, breached, cured, or waived.
- Cashflow posted, reversed, or allocated.
- Ledger entry posted or reconciled.
- NAV / valuation updated.
- Regulatory restriction triggered or cleared.
- Distribution calculated and paid.

Events requiring precision, replay, and audit:

- Contract term loading and amendment.
- Rule compilation.
- Capital call generation.
- Payment receipt / default determination.
- IC vote / consent.
- Compliance gate evaluation.
- Cashflow calculation.
- Waterfall calculation.
- Ledger posting.
- Report generation inputs.

Decisions that must not be delegated to an LLM:

- Arithmetic: fees, calls, interest, penalties, waterfalls.
- Threshold checks: vote percentages, veto existence, notice-day windows.
- Status commits: default, breach, approval, compliance block.
- Ledger posting and reconciliation.
- Event ordering and replay.
- Schema validation.

Where LLM helps:

- Propose clause-to-rule mappings from documents.
- Propose missing structured inputs for human review.
- Summarize soft risk, reputation risk, relationship trust, and negotiation posture.
- Generate narrative decision memos from deterministic facts.
- Rank which agents should review or object, without committing the result.

If no LLM exists, MVP must still run:

```text
fund_terms.yaml + scenario.yaml + agent_profiles.yaml
-> deterministic world compile
-> 12-month event queue
-> capital call / payment / default / IC approval / investment / reporting / distribution
-> event_log.jsonl + ledger + state_snapshot.json + report_context.json
```

If only one LLM agent is added, place it in the `DecisionEngine` as a non-committing advisor that writes `DecisionRecord.proposal`, `rationale`, and `confidence`. The `RuleEngine` must still validate and commit or reject.

Minimum verifiable MVP:

- One fund, one GP, one LP, one SPV, one portfolio company, one IC, one auditor, one regulator.
- Run 12 months.
- Branches: base case, LP late/default, IC rejection, regulatory delay, early liquidity.
- Deterministic cashflow and ledger reconciliation.
- OCEL-style event log with object refs.
- Report context readable by the existing report layer and by a future business report agent.

OASIS replacement point:

The new engine should sit after Zep graph + profile/config generation and before report generation. It should implement the same high-level lifecycle:

```text
create simulation
prepare simulation
run simulation
monitor status
write logs
export report context
generate report
```

## 2. Existing MiroFish Architecture: Reuse and Non-Reuse

### 2.1 Confirmed Current Flow

Current backend flow, confirmed from code:

```text
project documents
-> ontology_generator.py
-> graph_builder.py / Zep
-> zep_entity_reader.py
-> oasis_profile_generator.py
-> simulation_config_generator.py
-> simulation_manager.py
-> simulation_runner.py
-> backend/scripts/run_twitter_simulation.py or run_reddit_simulation.py
-> platform actions.jsonl
-> report_agent.py + zep_tools.py
```

Current files and roles:

- `backend/app/services/ontology_generator.py`: LLM generates exactly up to 10 Zep entity types and edge types; prompt is explicitly social-media opinion simulation oriented.
- `backend/app/services/graph_builder.py`: creates Zep standalone graph, dynamically builds Zep `EntityModel` / `EdgeModel`, sets ontology, batches document chunks into Zep, fetches graph nodes/edges.
- `backend/app/services/zep_entity_reader.py`: reads graph entities and enriches them with related edges/nodes for profile generation.
- `backend/app/services/oasis_profile_generator.py`: converts Zep entities to OASIS social profiles, including Reddit JSON and Twitter CSV shapes.
- `backend/app/services/simulation_config_generator.py`: creates social time config, social initial posts, agent activity, Twitter/Reddit platform config.
- `backend/app/services/simulation_manager.py`: owns simulation lifecycle and writes `state.json`, `simulation_config.json`, `reddit_profiles.json`, `twitter_profiles.csv`.
- `backend/app/services/simulation_runner.py`: starts OASIS subprocess scripts, monitors `twitter/actions.jsonl` and `reddit/actions.jsonl`, updates `run_state.json`, optionally writes activities back to Zep.
- `backend/scripts/action_logger.py`: defines the current JSONL action format for platform actions and round start/end.
- `backend/app/services/report_agent.py`: builds reports with Zep search tools and an OASIS interview tool. Prompt is currently future social prediction oriented.

### 2.2 Can Reuse

Reusable code / design ideas:

- Project/document ingestion and extracted text handling.
- Zep graph creation, ontology setting, graph search, node/edge retrieval.
- Task manager pattern and async preparation progress callbacks.
- Simulation directory convention under `backend/uploads/simulations/<simulation_id>/`.
- State files: `state.json`, `run_state.json`, `simulation.log`.
- Runner lifecycle: prepare -> start subprocess -> monitor log -> update status.
- Existing `actions.jsonl` monitoring idea, but generalized to engine log parser.
- Zep-backed report tools, especially graph statistics, entity search, panorama search.
- `enable_graph_memory_update` concept, but it should be opt-in and business-event aware.
- LLM profile/config generation pattern, with a new business profile/config generator.

### 2.3 Must Not Reuse As-Is

OASIS-specific assumptions to avoid:

- Entity types must be social speakers.
- Profiles must have `karma`, `friend_count`, `follower_count`, `statuses_count`, MBTI, social persona.
- Events are initial posts, scheduled posts, hot topics, narrative direction.
- Platform config is Twitter/Reddit recommendation and viral spread.
- Actions are `CREATE_POST`, `LIKE_POST`, `REPOST`, `FOLLOW`, `COMMENT`, `DO_NOTHING`.
- Logs are platform-specific `twitter/actions.jsonl` and `reddit/actions.jsonl`.
- Report prompts require social-media Agent quotes and interview tools.
- Simulation time is "active agents per hour" rather than contractual deadlines and event due dates.

### 2.4 Required API / Runner / Report Abstractions

Add an engine adapter boundary:

```python
class SimulationEngineAdapter(Protocol):
    engine_type: str

    def prepare(self, simulation_id: str, project_id: str, graph_id: str, requirement: str, document_text: str) -> PreparedSimulation: ...
    def start(self, simulation_id: str, max_steps: int | None = None) -> RunHandle: ...
    def read_log(self, simulation_id: str, offset: int) -> tuple[int, list[EngineEvent]]: ...
    def get_status(self, simulation_id: str) -> EngineStatus: ...
    def export_report_context(self, simulation_id: str) -> dict: ...
```

Short-term implementation:

- Keep current OASIS routes working.
- Add business-specific routes under `backend/app/api/business_simulation.py`.
- Add `engine_type` to new configs and states.
- Later refactor common runner code into `SimulationEngineAdapter`.

Switching model:

```json
{
  "simulation_id": "sim_xxx",
  "engine_type": "oasis_social" | "business_governance",
  "graph_id": "mirofish_xxx",
  "engine_config_path": "simulation_config.json or business/business_simulation_config.json",
  "report_context_path": "business/report_context.json"
}
```

## 3. New Engine Position in MiroFish Pipeline

The new engine should be a first-class MiroFish simulation backend:

```text
MiroFish Project
  documents
  extracted_text
  simulation_requirement
  ontology
  Zep graph
  graph entities
  simulation backend
    - oasis_social
    - business_governance
  report agent
```

Business-governance preparation:

```text
graph entities + extracted text + simulation requirement
-> business ontology hints
-> business_profiles.json
-> fund_terms.yaml
-> scenario.yaml
-> business_simulation_config.json
-> compiled_world.json
```

Business-governance run:

```text
compiled_world.json
-> deterministic event queue
-> RuleEngine / CashflowEngine / DecisionEngine
-> event_log.jsonl
-> ledger.jsonl
-> state_snapshot.json
-> report_context.json
```

## 4. OASIS Replacement / Adapter Design

### 4.0 Non-Negotiable Replacement Contract

The business-governance simulator is successful only if it can occupy the same product slot that OASIS currently occupies in MiroFish.

In concrete terms, it must satisfy this contract:

```text
MiroFish can choose:
  engine_type = oasis_social
  or
  engine_type = business_governance

Both engines must support:
  create simulation
  prepare simulation
  run simulation
  monitor run_state.json
  emit append-only event/action log
  export report-ready context
  feed report agent
```

For the new engine, "simulation" means simulating fund operations, not social-media activity:

```text
FundClosing
-> CapitalCallIssued
-> LPPaymentReceived or LPDefault
-> DealEvaluation
-> ComplianceCheck
-> ICMeeting
-> ICApproval or ICRejected
-> InvestmentExecution
-> QuarterlyReport
-> FollowOnDiscussion
-> LiquidityEvent
-> Distribution
-> AuditReview
```

The adapter must hide engine-specific differences from MiroFish's outer pipeline:

| MiroFish concern | OASIS today | Business-governance replacement |
|---|---|---|
| Profile generation | social personas from graph entities | business roles / authority / decision policies from graph entities |
| Config generation | social time/activity/platform config | fund terms / scenario / runtime config |
| Runtime | OASIS Twitter/Reddit environment | deterministic fund-governance DES runtime |
| Log | `twitter/actions.jsonl`, `reddit/actions.jsonl` | `business/event_log.jsonl` plus compatibility projection |
| State | social round/status counts | event cursor, branch, obligations, ledger, fund state |
| Report input | graph facts + social actions/interviews | graph facts + fund timeline/cashflow/decision/rule audit context |

Minimum replacement smoke test:

```bash
# after business prepare has written business_simulation_config.json
python backend/scripts/run_business_simulation.py \
  --config backend/uploads/simulations/<simulation_id>/business/business_simulation_config.json
```

Expected result:

```text
backend/uploads/simulations/<simulation_id>/
  run_state.json                         # status completed
  business/event_log.jsonl               # fund operation event history
  business/ledger.jsonl                  # balanced ledger postings
  business/branch_results.json           # scenario alternatives and impacts
  business/state_snapshot.json           # final fund state
  business/report_context.json           # report agent input
```

MiroFish should then be able to generate a fund-operation simulation report without OASIS being installed or running. OASIS remains optional for social-media simulations; it is not required for the business-governance engine.

Current smoke MVP API endpoints:

```text
GET  /api/business-simulation/demo
POST /api/business-simulation/run
GET  /api/business-simulation/<simulation_id>/status
GET  /api/business-simulation/<simulation_id>/report-context
POST /api/business-simulation/<simulation_id>/report
GET  /api/business-simulation/<simulation_id>/outputs/<filename>
```

The deterministic smoke report endpoint writes:

```text
backend/uploads/simulations/<simulation_id>/business/business_report.md
```

### 4.1 Directory Layout

Current OASIS directory:

```text
backend/uploads/simulations/<simulation_id>/
  state.json
  run_state.json
  simulation_config.json
  reddit_profiles.json
  twitter_profiles.csv
  twitter/actions.jsonl
  reddit/actions.jsonl
  simulation.log
```

Business engine directory:

```text
backend/uploads/simulations/<simulation_id>/
  state.json
  run_state.json
  simulation.log
  business/
    fund_terms.yaml
    scenario.yaml
    agent_profiles.yaml
    business_simulation_config.json
    business_profiles.json
    compiled_world.json
    event_log.jsonl
    ledger.jsonl
    decision_records.jsonl
    rule_execution_records.jsonl
    state_snapshot.json
    report_context.json
```

### 4.2 Adapter Responsibilities

`BusinessGovernanceAdapter.prepare()`:

- Read graph entities with `ZepEntityReader`.
- Map graph entities to business object candidates.
- Generate or accept `fund_terms.yaml`, `scenario.yaml`, `agent_profiles.yaml`.
- Validate schemas with Pydantic.
- Compile terms into executable rules.
- Save `business_simulation_config.json` and `compiled_world.json`.

`BusinessGovernanceAdapter.start()`:

- Launch `backend/scripts/run_business_simulation.py`.
- Pass `--config backend/uploads/simulations/<simulation_id>/business/business_simulation_config.json`.
- Monitor `business/event_log.jsonl`.
- Update common `run_state.json`.

`BusinessGovernanceAdapter.export_report_context()`:

- Read final state, event log, ledger, decisions, and rule executions.
- Assemble `report_context.json` with executive summaries, timelines, branch outcomes, cashflow summaries, obligations, exceptions, and evidence refs.

### 4.3 Log Compatibility

Do not force business events into social `action_type`. Instead use a common envelope and a compatibility projection.

Canonical business event:

```json
{
  "event_id": "evt_2026_001",
  "timestamp": "2026-01-15T09:00:00Z",
  "simulation_time": "2026-01-15",
  "scenario_id": "lp_12_months",
  "branch_id": "base",
  "event_type": "CapitalCallIssued",
  "actor_agents": ["agent_gp"],
  "touched_objects": [
    {"object_type": "Fund", "object_id": "fund_i", "qualifier": "fund"},
    {"object_type": "LP", "object_id": "lp_a", "qualifier": "recipient"},
    {"object_type": "Contract", "object_id": "lpa_fund_i", "qualifier": "authority"}
  ],
  "payload": {},
  "source": {
    "kind": "deterministic",
    "evidence_refs": ["fund_terms.yaml#capital_call.notice_days"]
  },
  "decision_record_refs": [],
  "rule_execution_refs": ["rule_exec_001"],
  "cashflow_refs": ["cashflow_001"],
  "ledger_entry_refs": ["ledger_001"],
  "state_transition_refs": ["state_tx_001"],
  "causal_parent_event_refs": ["evt_closing"]
}
```

Compatibility projection for current status UI:

```json
{
  "round": 3,
  "timestamp": "2026-01-15T09:00:00Z",
  "platform": "business",
  "agent_id": "agent_gp",
  "agent_name": "GP",
  "action_type": "CapitalCallIssued",
  "action_args": {
    "fund_id": "fund_i",
    "lp_id": "lp_a",
    "amount": 1000000
  },
  "result": "capital call issued; due 2026-01-30",
  "success": true
}
```

## 5. New Engine Architecture Summary

### 5.1 Core Concepts

`Entity`

- Any real-world object or party. Examples: Fund, LP, GP, SPV, PortfolioCompany, IC, Auditor, Regulator.

`RoleBinding`

- A relationship binding an entity to a role in a scope. Example: `LP-A` is `LimitedPartner` in `Fund I`; `GP` is `Manager` of `Fund I`.

`Agent`

- Decision-capable representation of an entity/role. It can propose intents. It cannot directly mutate state.

`Contract`

- Agreement or governance document with parties, effective dates, clauses, and evidence refs.

`Clause`

- Structured or semi-structured term extracted from LPA, side letter, subscription agreement, policy, or regulation.

`Norm`

- Non-executable expectation such as reporting cadence or fiduciary standard; may be compiled into obligations or rule checks.

`Rule`

- Deterministic executable function or rule spec. Example: "capital call due date = notice date + 10 business days".

`Obligation`

- Duty with owner, beneficiary, due date, status, evidence, and remedies.

`Event`

- Timestamped occurrence that touches one or more objects and may trigger rules.

`DecisionRecord`

- Record of a choice: proposed intents, voters, authority, evidence, validation result, and committed outcome.

`RuleExecutionRecord`

- Audit record of rule id, inputs, outputs, pass/fail, and state changes.

`Cashflow`

- Economic movement request or result, such as capital call, LP payment, investment funding, fee, distribution.

`LedgerEntry`

- Double-entry-style accounting record with debit/credit or signed posting lines. Must reconcile.

`SimulationState`

- Current world state: objects, obligations, balances, portfolio positions, branch metadata, and event cursor.

`ScenarioConfig`

- Time horizon, initial events, market assumptions, branches, LLM policy, random seed, output settings.

`ScenarioBranch`

- Fork of state with branch trigger and parent branch ref.

`WorldCompiler`

- Converts graph entities + YAML terms + scenarios into validated executable world objects, rules, initial state, and event queue.

`EventQueue`

- Ordered queue of scheduled events. MVP: Python `heapq`.

`RuleEngine`

- Runs deterministic rules and validators. Owns commit authority.

`CashflowEngine`

- Calculates capital calls, payments, fees, penalties, investment funding, distributions, and ledger postings.

`DecisionEngine`

- Produces decision records. MVP supports rule-based decisions and optional LLM proposals.

`ReportContextAssembler`

- Converts raw logs/state into a stable report input.

`SimulationEngineAdapter`

- MiroFish integration interface for prepare/run/status/log/report.

### 5.2 Commit Flow

```text
Event arrives
-> collect touched objects
-> load applicable rules/clauses/obligations
-> optional agent/LLM intent
-> validate intent
-> execute deterministic rules
-> post cashflow/ledger if needed
-> apply state transition
-> write event + decision + rule execution + ledger logs
-> schedule follow-up events
```

## 6. Core Data Models

MVP should use Pydantic v2 models and YAML/JSON files.

### 6.1 `fund_terms.yaml`

```yaml
schema_version: "0.1"
fund:
  id: fund_i
  name: "Fund I"
  currency: USD
  vintage_year: 2026
  term_months: 120
  investment_period_months: 60

parties:
  gps:
    - id: gp
      name: "GP"
      entity_ref: "zep:node:gp"
  lps:
    - id: lp_a
      name: "LP-A"
      entity_ref: "zep:node:lp_a"
      commitment: 10000000
      side_letter_refs: [side_letter_lp_a]
  spvs:
    - id: spv_a
      name: "SPV-A"
  portfolio_companies:
    - id: portco_a
      name: "PortfolioCo-A"
      sector: "AI Infrastructure"

contracts:
  - id: lpa_fund_i
    type: LPA
    effective_date: "2026-01-01"
    parties: [fund_i, gp, lp_a]
    clauses:
      - id: clause_mgmt_fee
        type: management_fee
        text_ref: "document:lpa.pdf#p12"
        parameters:
          basis: committed_capital
          annual_rate: 0.02
          frequency: quarterly
      - id: clause_carry
        type: carry
        text_ref: "document:lpa.pdf#p24"
        parameters:
          carry_rate: 0.20
          hurdle_rate: 0.08
          catchup: true
      - id: clause_capital_call_notice
        type: capital_call_notice
        parameters:
          notice_days: 10
          business_days: true
      - id: clause_default_penalty
        type: default_penalty
        parameters:
          grace_days: 5
          penalty_rate_annual: 0.12
          remedies: [interest, suspend_voting_rights]
      - id: clause_voting_threshold
        type: voting_threshold
        parameters:
          matter: investment_approval
          threshold_percent: 66.67
          voters: IC
      - id: clause_reporting_obligation
        type: reporting_obligation
        parameters:
          report_type: quarterly_report
          due_days_after_quarter_end: 45
      - id: clause_waterfall
        type: waterfall_rule
        parameters:
          tiers:
            - name: return_of_capital
              recipient: LPs
              priority: 1
            - name: preferred_return
              recipient: LPs
              priority: 2
              rate: 0.08
            - name: catchup
              recipient: GP
              priority: 3
            - name: carry_split
              priority: 4
              split:
                LPs: 0.80
                GP: 0.20
      - id: clause_regulatory_restriction
        type: compliance_restriction
        parameters:
          restricted_sector: "sanctioned_entity"
          action: block_investment

side_letters:
  - id: side_letter_lp_a
    lp_id: lp_a
    clauses:
      - id: side_veto_sensitive_sector
        type: veto_right
        parameters:
          matters: [restricted_sector_investment]
          notice_days: 5
```

### 6.2 `scenario.yaml`

```yaml
schema_version: "0.1"
scenario:
  id: lp_12_months
  name: "LP enters Fund I and 12-month operations"
  start_date: "2026-01-01"
  end_date: "2026-12-31"
  random_seed: 42

market_parameters:
  base_exit_probability: 0.10
  regulatory_delay_probability: 0.15
  liquidity_event_month: 10

llm_policy:
  enabled: false
  allowed_for:
    - soft_risk_assessment
    - decision_memo_draft
  forbidden_for:
    - ledger_posting
    - waterfall_calculation
    - default_status_commit

initial_events:
  - event_type: FundClosing
    simulation_time: "2026-01-02"
    actor_agents: [agent_gp]
    payload:
      fund_id: fund_i
  - event_type: InitialCapitalCall
    simulation_time: "2026-01-15"
    actor_agents: [agent_gp]
    payload:
      fund_id: fund_i
      lp_id: lp_a
      amount: 1000000

branch_triggers:
  - id: lp_default_branch
    trigger_event_type: CapitalCallDue
    condition: "payment_received == false"
    branch_id: lp_default
  - id: ic_rejection_branch
    trigger_event_type: ICMeeting
    condition: "approval_votes_percent < threshold_percent"
    branch_id: ic_rejection
  - id: regulatory_delay_branch
    trigger_event_type: ComplianceCheck
    condition: "regulatory_delay == true"
    branch_id: regulatory_delay
  - id: early_liquidity_branch
    trigger_event_type: LiquidityEventCheck
    condition: "liquidity_event == true"
    branch_id: early_liquidity

output:
  write_event_log: true
  write_ledger: true
  write_snapshots:
    frequency: month_end
  write_report_context: true
```

### 6.3 `agent_profiles.yaml`

```yaml
schema_version: "0.1"
agents:
  - id: agent_gp
    role: GeneralPartner
    entity_id: gp
    represents: gp
    risk_tolerance: high
    liquidity_preference: medium
    governance_sensitivity: medium
    trust_relationships:
      lp_a: 0.7
      regulator: 0.5
    decision_policy:
      type: rule_based
      objectives: [deploy_capital, maintain_compliance, preserve_lp_relationship]
    communication_style: concise_formal
    memory_hooks:
      zep_entity_uuid: "zep:node:gp"

  - id: agent_lp_a
    role: LimitedPartner
    entity_id: lp_a
    represents: lp_a
    risk_tolerance: medium
    liquidity_preference: high
    governance_sensitivity: high
    decision_policy:
      type: threshold_guarded
      veto_on: [restricted_sector_investment]
```

### 6.4 `business_simulation_config.json`

```json
{
  "schema_version": "0.1",
  "engine_type": "business_governance",
  "simulation_id": "sim_xxx",
  "project_id": "proj_xxx",
  "graph_id": "mirofish_xxx",
  "input_paths": {
    "fund_terms": "business/fund_terms.yaml",
    "scenario": "business/scenario.yaml",
    "agent_profiles": "business/agent_profiles.yaml"
  },
  "output_paths": {
    "compiled_world": "business/compiled_world.json",
    "event_log": "business/event_log.jsonl",
    "ledger": "business/ledger.jsonl",
    "decision_records": "business/decision_records.jsonl",
    "rule_execution_records": "business/rule_execution_records.jsonl",
    "state_snapshot": "business/state_snapshot.json",
    "report_context": "business/report_context.json"
  },
  "runtime": {
    "event_queue": "heapq",
    "max_events": 10000,
    "snapshot_frequency": "month_end"
  },
  "llm": {
    "enabled": false,
    "model": "",
    "base_url": "",
    "commit_policy": "propose_only"
  }
}
```

### 6.5 `business_profiles.json`

This replaces `reddit_profiles.json` / `twitter_profiles.csv` for the business engine.

```json
[
  {
    "agent_id": "agent_gp",
    "agent_name": "GP",
    "role": "GeneralPartner",
    "entity_id": "gp",
    "source_entity_uuid": "zep:node:gp",
    "authority_scope": ["capital_call", "deal_proposal", "reporting"],
    "decision_policy": {
      "kind": "rule_based",
      "risk_tolerance": "high",
      "liquidity_preference": "medium",
      "governance_sensitivity": "medium"
    }
  }
]
```

### 6.6 `event_log.jsonl`

Each line is one event. It is OCEL-style: one event can touch many objects with qualifiers.

Required fields:

```json
{
  "event_id": "evt_0001",
  "timestamp": "2026-06-30T00:00:00Z",
  "simulation_time": "2026-01-15",
  "scenario_id": "lp_12_months",
  "branch_id": "base",
  "event_type": "CapitalCallIssued",
  "actor_agents": ["agent_gp"],
  "touched_objects": [
    {"object_type": "Fund", "object_id": "fund_i", "qualifier": "fund"},
    {"object_type": "LP", "object_id": "lp_a", "qualifier": "recipient"}
  ],
  "payload": {},
  "source": {
    "kind": "deterministic",
    "evidence_refs": ["fund_terms.yaml#contracts[0].clauses.clause_capital_call_notice"]
  },
  "decision_record_refs": [],
  "rule_execution_refs": [],
  "cashflow_refs": [],
  "ledger_entry_refs": [],
  "state_transition_refs": [],
  "causal_parent_event_refs": []
}
```

### 6.7 `state_snapshot.json`

```json
{
  "schema_version": "0.1",
  "simulation_id": "sim_xxx",
  "scenario_id": "lp_12_months",
  "branch_id": "base",
  "as_of_simulation_time": "2026-12-31",
  "objects": {
    "funds": {
      "fund_i": {
        "status": "active",
        "called_capital": 1000000,
        "paid_in_capital": 1000000,
        "unfunded_commitments": 9000000,
        "nav": 1150000
      }
    },
    "lps": {
      "lp_a": {
        "commitment": 10000000,
        "paid_in": 1000000,
        "default_status": "none",
        "distributions_received": 0
      }
    },
    "obligations": {},
    "portfolio_positions": {}
  },
  "ledger_summary": {
    "debits": 1000000,
    "credits": 1000000,
    "balanced": true
  }
}
```

### 6.8 `report_context.json`

```json
{
  "schema_version": "0.1",
  "simulation_id": "sim_xxx",
  "engine_type": "business_governance",
  "title": "Fund I 12-Month Governance Simulation",
  "scenario_summary": {
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
    "branches": ["base", "lp_default", "ic_rejection", "regulatory_delay", "early_liquidity"]
  },
  "executive_findings": [
    "Base case completes initial capital call and investment execution.",
    "LP default branch triggers penalty and suspended voting rights."
  ],
  "timeline": [
    {
      "simulation_time": "2026-01-15",
      "event_type": "CapitalCallIssued",
      "summary": "GP issued USD 1,000,000 capital call to LP-A.",
      "object_refs": ["fund_i", "lp_a", "lpa_fund_i"],
      "evidence_refs": ["event_log.jsonl#evt_0002"]
    }
  ],
  "cashflow_summary": {
    "capital_called": 1000000,
    "capital_paid": 1000000,
    "distributions": 0,
    "fees": 50000,
    "penalties": 0
  },
  "governance_summary": {
    "decisions": 3,
    "approvals": 2,
    "rejections": 1,
    "vetoes": 0
  },
  "exceptions": [],
  "report_agent_hints": {
    "recommended_sections": [
      "Scenario and Object Map",
      "Capital Calls and Cashflow",
      "Governance Decisions",
      "Branch Risk Comparison",
      "Audit Trail"
    ]
  }
}
```

### 6.9 Mapping From Existing MiroFish Files

| Existing OASIS file | Business replacement |
|---|---|
| `simulation_config.json` | `business/business_simulation_config.json` plus `fund_terms.yaml` and `scenario.yaml` |
| `reddit_profiles.json` | `business/business_profiles.json` or `business/agent_profiles.yaml` |
| `twitter_profiles.csv` | Not needed for business engine |
| `twitter/actions.jsonl`, `reddit/actions.jsonl` | `business/event_log.jsonl` plus optional compatibility projection |
| `simulation.log` | Keep |
| `run_state.json` | Keep common fields; add `engine_type` and `business_events_count` |

## 7. MVP Runtime Design

### 7.1 Proposed Modules

```text
backend/app/services/business_simulation/
  __init__.py
  models.py
  loader.py
  compiler.py
  engine.py
  events.py
  rules.py
  cashflow.py
  decisions.py
  logging.py
  report_context.py
  adapter.py

backend/app/api/business_simulation.py
backend/scripts/run_business_simulation.py
backend/uploads/simulations/<simulation_id>/business/
```

Module responsibilities:

- `models.py`: Pydantic models for terms, scenario, agents, events, state, cashflows, ledger, records.
- `loader.py`: read YAML/JSON, resolve paths, validate schema versions.
- `compiler.py`: build `CompiledWorld` from terms/scenario/agents/Zep mappings.
- `events.py`: event registry, event classes, scheduling helpers.
- `engine.py`: heap queue, run loop, event dispatch, branch management.
- `rules.py`: deterministic rules and validators.
- `cashflow.py`: capital call, payment, fee, penalty, investment, waterfall, ledger.
- `decisions.py`: decision records, rule-based decisions, optional LLM sidecar proposals.
- `logging.py`: JSONL writers and compatibility projection.
- `report_context.py`: summarizer for report agent.
- `adapter.py`: MiroFish lifecycle adapter.

### 7.2 Core Pseudocode

```python
def load_world(config_path: str) -> RawWorld:
    config = load_json(config_path)
    fund_terms = load_yaml(resolve(config.input_paths.fund_terms))
    scenario = load_yaml(resolve(config.input_paths.scenario))
    agents = load_yaml(resolve(config.input_paths.agent_profiles))
    return RawWorld.validate(fund_terms=fund_terms, scenario=scenario, agents=agents)
```

```python
def compile_world(raw: RawWorld) -> CompiledWorld:
    objects = compile_objects(raw.fund_terms)
    role_bindings = compile_role_bindings(raw.fund_terms, raw.agents)
    rules = compile_rules(raw.fund_terms.contracts)
    obligations = compile_initial_obligations(rules, raw.scenario)
    initial_state = SimulationState(objects=objects, obligations=obligations)
    queue = EventQueue()
    for event in raw.scenario.initial_events:
        queue.push(event.simulation_time, event)
    return CompiledWorld(objects, role_bindings, rules, initial_state, queue)
```

```python
def schedule_event(queue: EventQueue, event: Event) -> None:
    heapq.heappush(queue.heap, (event.simulation_time, event.priority, event.event_id, event))
```

```python
def run_simulation(world: CompiledWorld, outputs: OutputWriters) -> SimulationState:
    state = world.initial_state
    while world.queue and state.event_count < world.max_events:
        event = world.queue.pop()
        result = apply_event(event, state, world)
        outputs.write_all(result)
        for follow_up in result.follow_up_events:
            schedule_event(world.queue, follow_up)
        if should_snapshot(event):
            outputs.write_snapshot(state)
    outputs.write_report_context(export_report_context(state, outputs))
    return state
```

```python
def apply_event(event: Event, state: SimulationState, world: CompiledWorld) -> EventResult:
    intent = event.payload.get("intent")
    decision = validate_intent(intent, event, state, world)
    rule_records = []
    state_transitions = []

    for rule in world.rules.for_event(event.event_type):
        record, transitions = execute_rule(rule, event, state)
        rule_records.append(record)
        state_transitions.extend(transitions)

    cashflows, ledger_entries = post_cashflow(event, state, world)
    commit_state(state, state_transitions, cashflows, ledger_entries)

    canonical_event = enrich_event(
        event,
        decision_record_refs=[decision.id] if decision else [],
        rule_execution_refs=[r.id for r in rule_records],
        cashflow_refs=[c.id for c in cashflows],
        ledger_entry_refs=[l.id for l in ledger_entries],
    )
    return EventResult(canonical_event, decision, rule_records, cashflows, ledger_entries)
```

```python
def validate_intent(intent: dict | None, event: Event, state: SimulationState, world: CompiledWorld) -> DecisionRecord | None:
    if intent is None:
        return None
    validators = world.rules.validators_for(intent["type"])
    results = [v.check(intent, state) for v in validators]
    accepted = all(r.passed for r in results)
    return DecisionRecord(
        intent=intent,
        validation_results=results,
        committed=accepted,
        commit_policy="deterministic_validators_only",
    )
```

```python
def execute_rule(rule: Rule, event: Event, state: SimulationState) -> tuple[RuleExecutionRecord, list[StateTransition]]:
    inputs = rule.collect_inputs(event, state)
    output = rule.fn(inputs)
    transitions = rule.to_transitions(output)
    return RuleExecutionRecord(rule_id=rule.id, inputs=inputs, output=output, passed=output.passed), transitions
```

```python
def post_cashflow(event: Event, state: SimulationState, world: CompiledWorld) -> tuple[list[Cashflow], list[LedgerEntry]]:
    if event.event_type == "CapitalCallIssued":
        return CashflowEngine.create_capital_call(event, state)
    if event.event_type == "LPPaymentReceived":
        return CashflowEngine.receive_payment(event, state)
    if event.event_type == "Distribution":
        return CashflowEngine.apply_waterfall(event, state)
    return [], []
```

```python
def snapshot_state(state: SimulationState, path: str) -> None:
    write_json(path, state.model_dump(mode="json"))
```

```python
def export_report_context(state: SimulationState, logs: LogIndex) -> dict:
    return ReportContextAssembler(state=state, logs=logs).assemble()
```

## 8. LP 12-Month Demo Scenario

Scenario:

```text
LP-A enters Fund I. Over 12 months, the fund closes, calls capital, evaluates a deal,
holds an IC meeting, invests, reports quarterly, handles follow-on discussion,
possibly exits early, distributes proceeds, and undergoes audit review.
```

Initial entities:

- Fund
- LP-A
- GP
- SPV
- PortfolioCo-A
- IC
- Legal Counsel
- Auditor
- Regulator

### 8.1 Event Sequence

| Event | Trigger | Rule-based part | LLM decision? | State changes | Logs / cashflow / report use |
|---|---|---|---|---|---|
| `FundClosing` | Initial event on start date. | Verify fund, GP, LP, commitment, LPA effective date. | No. | Fund status `active`; LP commitment recorded; initial obligations created. | Event log links Fund, GP, LP, LPA; report shows scenario setup. |
| `InitialCapitalCall` | Scheduled after closing. | Check authority, notice days, commitment availability, call amount <= unfunded. | No. | Creates capital call obligation and due date. | Cashflow `capital_call`; ledger memo entry; report cashflow timeline. |
| `CapitalCallIssued` | Output of capital call rule. | Validate notice and amount. | No. | LP payable obligation. | Event log with clause refs. |
| `LPPaymentReceived` | Payment arrives before due date in base branch. | Match payment to call, update paid-in and unfunded. | No. | Paid-in increases, obligation fulfilled. | Ledger debit cash / credit capital contribution. |
| `LPDefault` | Branch trigger when payment absent after grace days. | Apply default status, penalty interest, voting suspension if clause says so. | No. | LP default status; penalty obligation; suspended rights. | Exception and risk summary. |
| `DealEvaluation` | Month 2 scheduled event. | Check investment period, available capital, prohibited sector. | Optional for soft risk memo only. | Creates deal candidate and diligence obligation. | Report explains investment funnel. |
| `ComplianceCheck` | Deal evaluation follow-up. | Check restrictions, side letters, regulator delay branch. | Optional to summarize regulatory risk, not commit. | Pass/block/delay status. | Branch comparison. |
| `ICMeeting` | Compliance pass or delay resolved. | Check quorum, threshold, eligible voters. | Optional to draft memo. | DecisionRecord created. | Governance section. |
| `ICApproval` | Votes meet threshold. | Commit approval and authorize investment execution. | No. | Deal approved; investment execution obligation. | Decision audit. |
| `ICRejected` | Votes miss threshold. | Commit rejection; release reserved capital. | No. | Deal rejected; branch state. | Branch risk finding. |
| `InvestmentExecution` | Approval + funds available. | Post funding, create portfolio position. | No. | Cash leaves fund; holding created. | Ledger and portfolio state. |
| `QuarterlyReport` | Quarter-end + reporting due rule. | Check due date, required recipients, contents. | LLM may draft narrative, not facts. | Reporting obligation fulfilled or late. | Report context aligns to ILPA-like sections. |
| `FollowOnDiscussion` | Month 7 portfolio need. | Check reserves and authorization requirements. | Optional for soft risk. | Creates follow-on decision candidate. | Timeline and governance workload. |
| `LiquidityEventCheck` | Month 10 market trigger. | Deterministic branch trigger from scenario params/seed. | No. | Branch `early_liquidity` if true. | Branch outcome. |
| `LiquidityEvent` | Early liquidity branch. | Calculate proceeds and available distributions. | No. | Cash proceeds received. | Ledger proceeds. |
| `Distribution` | Proceeds available. | Apply waterfall, hurdle/carry rules. | No. | LP/GP distribution obligations and ledger entries. | Cashflow summary and waterfall explanation. |
| `AuditReview` | Month 12 scheduled. | Reconcile ledger, obligations, decisions, missing evidence. | No. | Audit findings. | Final audit section. |

### 8.2 Branches

Base case:

- LP pays on time.
- Compliance passes.
- IC approves.
- Investment executed.
- Quarterly report delivered.
- No early liquidity unless scenario seed triggers it.

LP late/default:

- `CapitalCallDue` finds no payment.
- `LPDefault` applies grace days and penalty.
- Voting rights may suspend.
- Report highlights liquidity and governance risk.

IC rejection:

- `ICMeeting` vote below threshold.
- Deal rejected; no investment ledger posting.
- Report compares avoided risk and deployment delay.

Regulatory delay:

- Compliance check blocks immediate execution.
- Schedules delayed review.
- If resolved, proceeds to IC; if not, branch remains blocked.

Early liquidity:

- Month 10 liquidity trigger.
- Proceeds posted.
- Distribution waterfall runs.
- Report shows economic upside and carry/hurdle effects.

### 8.3 Report Agent Consumption

MVP report strategy:

- Existing report agent can still use Zep for project context.
- Business engine should provide `report_context.json` for event/cashflow facts.
- Add a business report tool later:

```python
get_business_report_context(simulation_id)
get_business_timeline(simulation_id, branch_id=None)
get_cashflow_summary(simulation_id, branch_id=None)
get_rule_audit(simulation_id, object_id=None)
get_branch_comparison(simulation_id)
```

Short-term, report generation can read `report_context.json` and inject it into a business-specific report prompt.

## 9. Technology Selection

### 9.1 MVP Recommendation

Use:

- Python.
- Pydantic v2.
- YAML input plus JSON outputs.
- `heapq` event queue.
- Plain Python rule functions.
- JSONL event, decision, rule, and ledger logs.
- Optional LLM sidecar with `commit_policy = propose_only`.
- Zep only as graph/memory context, not as the simulation state store.

Do not use in MVP:

- SimPy: useful later, but `heapq` is enough for a 12-month fund scenario.
- Mesa: agent-first and adds conceptual weight.
- Temporal: deployment complexity is too high for local simulation MVP.
- BPMN/Camunda: premature process engine.
- DMN/FEEL: valuable later, but initial rule DSL should stay Python/Pydantic.
- LangGraph/AutoGen/CrewAI: do not let agent orchestration define legal/financial truth.
- Drools/PyRete: rule engine complexity before rule shapes stabilize.
- Postgres: JSONL + snapshots are enough for MVP; add DB when querying becomes painful.
- Full OCEL/PM4Py integration: design for it, export later.

### 9.2 Product-Stage Recommendation

Introduce when needed:

- SimPy: if concurrent resource queues, long-running process waits, or shared capacity become complex.
- DMN: if non-engineers need editable decision tables for thresholds/default/remedies.
- PM4Py: once event logs are rich enough for conformance and process discovery.
- Postgres: when simulation histories need UI querying, branch diff, and multi-user persistence.
- Business report tools: replace OASIS social report prompt/tools with engine-specific report tools.

### 9.3 Research-Stage Recommendation

Consider:

- Mesa: compare agent policies across many LP/GP behavioral assumptions.
- Concordia: test richer generative social/governance interactions, but keep deterministic commit layer.
- LangGraph / AutoGen / CrewAI: orchestrate advisor agents for due diligence memos, negotiation proposals, and board discussion simulations.
- Temporal: convert validated simulation workflows into real operational workflows.
- BPMN export/import: explain process maps to business users.
- OCEL 2.0 full export: support external process mining tools.

### 9.4 Deployment Complexity Impact

Low complexity:

- Python modules, Pydantic, YAML/JSON/JSONL, `heapq`.

Medium complexity:

- SimPy, PM4Py, Postgres, custom report tools.

High complexity:

- Temporal service, Camunda, Drools, full LangGraph platform deployment, multi-agent frameworks with persistent runtime.

## 10. 2-4 Week MVP Development Plan

### Week 1: Schema and World Kernel

Deliverables:

- `backend/app/services/business_simulation/models.py`
- `loader.py`
- `compiler.py`
- first versions of `fund_terms.yaml`, `scenario.yaml`, `agent_profiles.yaml`
- `SimulationEngineAdapter` interface draft
- sample `business_simulation_config.json`

Tasks:

- Define Pydantic models.
- Validate YAML and JSON paths.
- Compile entities, role bindings, contracts, clauses, obligations.
- Implement event queue with `heapq`.
- Define canonical `event_log.jsonl` envelope.

Acceptance:

- Invalid terms fail with readable validation errors.
- A compiled world can schedule `FundClosing` and `InitialCapitalCall`.

### Week 2: Rules, Cashflow, and Base Scenario

Deliverables:

- `rules.py`
- `cashflow.py`
- `engine.py`
- `logging.py`
- `backend/scripts/run_business_simulation.py`
- base 12-month demo scenario.

Tasks:

- Implement capital call, due date, LP payment, default, management fee, investment execution.
- Implement ledger posting and balance check.
- Write `event_log.jsonl`, `ledger.jsonl`, `state_snapshot.json`.
- Implement run script with `--config`.

Acceptance:

- Base scenario runs end-to-end offline.
- Ledger balances.
- State snapshot matches expected called/paid/unfunded numbers.

### Week 3: Branching, Decisions, LLM Sidecar, Report Context

Deliverables:

- `decisions.py`
- branch support in `engine.py`
- `decision_records.jsonl`
- `rule_execution_records.jsonl`
- `report_context.py`
- optional LLM proposal interface.

Tasks:

- Implement LP default, IC rejection, regulatory delay, early liquidity branches.
- Implement decision records and rule execution audit records.
- Implement `ReportContextAssembler`.
- Add minimal API endpoint draft in `backend/app/api/business_simulation.py`.

Acceptance:

- Same seed produces same branch results.
- LLM disabled path is fully functional.
- LLM enabled path cannot commit invalid state.

### Week 4: Tests, Demo, Documentation, Minimal UI Hook

Deliverables:

- Unit tests and golden output fixtures.
- Demo run under `backend/uploads/simulations/<simulation_id>/business/`.
- Documentation update.
- Optional timeline visualization endpoint.
- Comparison doc: OASIS `actions.jsonl` vs business `event_log.jsonl`.

Tasks:

- Add tests for schema validation, capital call, default, IC threshold, waterfall, replay.
- Add replay test: event log reconstructs final state.
- Add report context test.
- Add API smoke test.

Acceptance:

- `pytest` passes.
- Demo scenario runs from CLI.
- Final state reproducible from seed and input files.
- Generated `report_context.json` has all required fields.

## 11. Risk List

Technical risks:

- Current ontology prompt is social-media-specific; business ontology generation needs a separate prompt or mode.
- Current report prompt is social prediction oriented; business report quality will be poor unless prompts/tools are separated.
- Zep graph extraction may miss exact legal terms; MVP must allow human-authored YAML.
- JSONL logs can grow; acceptable for MVP, but query UX will need indexing later.
- Branch explosion if scenarios are not bounded.
- LLM sidecar may hallucinate; never let it commit.

Domain risks:

- Fund terms vary widely across jurisdictions and fund strategies.
- Waterfall rules can be complex and require expert review.
- Side letters can conflict with LPA terms.
- Regulatory restrictions are jurisdiction-specific.
- ILPA alignment helps reporting, but does not validate legal correctness.

Product risks:

- Users may expect PDF contract extraction too early.
- Users may confuse "simulation" with legal/financial advice.
- Reports must clearly label assumptions and simulated outcomes.

Required domain expert input:

- Fund term schema coverage.
- Capital call / default / waterfall examples.
- IC voting and veto examples.
- Report context fields aligned to expected LP/GP workflows.
- Legal disclaimer and review boundaries.

## 12. Next Concrete Actions

Immediate engineering actions:

1. Add `backend/app/services/business_simulation/` package skeleton.
2. Add Pydantic models for terms, scenario, agents, events, state, cashflows, ledger, decisions, rule executions.
3. Create sample `backend/uploads/simulations/demo_business/business/` fixtures.
4. Implement deterministic base scenario without LLM.
5. Add `run_business_simulation.py`.
6. Add golden tests for capital call, payment, default, IC rejection, distribution, and replay.
7. Add `report_context.json` assembler.
8. Add business-specific report prompt/tool interface.

First MVP test cases:

- `test_compile_minimal_fund_terms`
- `test_capital_call_notice_due_date`
- `test_lp_payment_reduces_unfunded_commitment`
- `test_lp_default_after_grace_period`
- `test_ic_approval_threshold`
- `test_ic_rejection_branch`
- `test_regulatory_delay_branch`
- `test_distribution_waterfall_balances_ledger`
- `test_event_log_replay_reconstructs_final_state`
- `test_report_context_contains_timeline_cashflow_governance`

Definition of done:

- A developer can run one command:

```bash
python backend/scripts/run_business_simulation.py \
  --config backend/uploads/simulations/demo_business/business/business_simulation_config.json
```

- The run writes:

```text
business/event_log.jsonl
business/ledger.jsonl
business/decision_records.jsonl
business/rule_execution_records.jsonl
business/state_snapshot.json
business/report_context.json
```

- The final ledger balances.
- The final state is reproducible from the same inputs and random seed.
- The report context can be consumed without reading OASIS-specific files.

## Sources Used

- OASIS paper: https://arxiv.org/abs/2411.11581
- ILPA templates hub: https://ilpa.org/industry-guidance/templates-standards-model-documents/
- ILPA template endorsement/adoption details: https://ilpa.org/industry-guidance/templates-standards-model-documents/reporting-template/reporting-template-endorsement-adoption/
- OCEL 2.0 standard site: https://www.ocel-standard.org/
- OCEL 2.0 specification: https://arxiv.org/abs/2403.01975
- OMG BPMN specification page: https://www.omg.org/spec/BPMN/
- OMG DMN specification page: https://www.omg.org/spec/DMN/
- SimPy documentation: https://simpy.readthedocs.io/en/latest/
- Mesa documentation: https://mesa.readthedocs.io/latest/
- Temporal documentation: https://docs.temporal.io/
- LangGraph documentation: https://docs.langchain.com/oss/python/langgraph/overview
- Microsoft AutoGen documentation: https://microsoft.github.io/autogen/stable/
- CrewAI documentation: https://docs.crewai.com/
- Concordia repository: https://github.com/google-deepmind/concordia
- PM4Py overview: https://processintelligence.solutions/pm4py
