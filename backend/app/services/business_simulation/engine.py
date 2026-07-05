"""Minimal deterministic fund-operation simulator."""

from __future__ import annotations

import heapq
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .loader import load_structured_file, write_json
from .logging import JsonlWriter
from .models import (
    BusinessEvent,
    DecisionRecord,
    EventSource,
    LedgerEntry,
    LedgerLine,
    ObjectRef,
    RuleExecutionRecord,
    RunResult,
    RuntimeState,
)
from .report_context import assemble_report_context


class BusinessSimulationEngine:
    """Run the MVP business-governance simulation from a config file."""

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path).resolve()
        self.base_dir = self.config_path.parent
        self.config = load_structured_file(self.config_path)
        self.fund_terms = load_structured_file(self._resolve_input("fund_terms"))
        self.scenario = load_structured_file(self._resolve_input("scenario"))
        self.agent_profiles = load_structured_file(self._resolve_input("agent_profiles"))

        output_paths = self.config["output_paths"]
        self.event_writer = JsonlWriter(self._resolve_output(output_paths["event_log"]))
        self.ledger_writer = JsonlWriter(self._resolve_output(output_paths["ledger"]))
        self.decision_writer = JsonlWriter(self._resolve_output(output_paths["decision_records"]))
        self.rule_writer = JsonlWriter(self._resolve_output(output_paths["rule_execution_records"]))
        self.compiled_world_path = self._resolve_output(output_paths["compiled_world"])
        self.branch_results_path = self._resolve_output(output_paths.get("branch_results", "branch_results.json"))
        self.state_path = self._resolve_output(output_paths["state_snapshot"])
        self.report_context_path = self._resolve_output(output_paths["report_context"])
        self.evidence_bindings_path = self.base_dir / "evidence_bindings.json"
        self.run_state_path = self.base_dir.parent / "run_state.json"

        scenario_data = self.scenario["scenario"]
        self.state = self._initial_state(
            simulation_id=self.config["simulation_id"],
            scenario_id=scenario_data["id"],
        )
        self.events: list[BusinessEvent] = []
        self.ledger_entries: list[LedgerEntry] = []
        self.decisions: list[DecisionRecord] = []
        self.rule_records: list[RuleExecutionRecord] = []
        self.queue: list[tuple[str, int, dict[str, Any]]] = []
        self.sequence = 0

    @property
    def fund_id(self) -> str:
        return self.fund_terms["fund"]["id"]

    @property
    def fund_name(self) -> str:
        return self.fund_terms["fund"].get("name", self.fund_id)

    @property
    def gp_id(self) -> str:
        return self.fund_terms["parties"]["gps"][0]["id"]

    @property
    def gp_name(self) -> str:
        return self.fund_terms["parties"]["gps"][0].get("name", self.gp_id)

    @property
    def lp_id(self) -> str:
        return self.fund_terms["parties"]["lps"][0]["id"]

    @property
    def lp_name(self) -> str:
        return self.fund_terms["parties"]["lps"][0].get("name", self.lp_id)

    @property
    def portfolio_company_id(self) -> str:
        return self.fund_terms["parties"].get("portfolio_companies", [{}])[0].get("id", "portco_a")

    @property
    def portfolio_company_name(self) -> str:
        return self.fund_terms["parties"].get("portfolio_companies", [{}])[0].get("name", self.portfolio_company_id)

    def _clause_parameters(self, clause_type: str) -> dict[str, Any]:
        for contract in self.fund_terms.get("contracts", []):
            for clause in contract.get("clauses", []):
                if clause.get("type") == clause_type:
                    return clause.get("parameters", {})
        return {}

    def _lp_commitment(self) -> float:
        return float(self.fund_terms["parties"]["lps"][0].get("commitment", 0))

    def _management_fee_amount(self) -> float:
        params = self._clause_parameters("management_fee")
        annual_rate = float(params.get("annual_rate", 0))
        period_months = float(params.get("period_months", 3))
        basis = params.get("basis", "committed_capital")
        basis_amount = self._lp_commitment() if basis == "committed_capital" else self.state.funds[self.fund_id].get("paid_in_capital", 0)
        return round(basis_amount * annual_rate * period_months / 12, 2)

    def _ic_threshold_percent(self) -> float:
        params = self._clause_parameters("voting_threshold")
        return float(params.get("threshold_percent", 66.67))

    def _waterfall(self, amount: float) -> dict[str, float]:
        params = self._clause_parameters("waterfall_rule")
        paid_in = float(self.state.lps[self.lp_id].get("paid_in", 0))
        remaining = amount

        return_of_capital = min(remaining, paid_in) if params.get("return_of_capital", True) else 0.0
        remaining = round(remaining - return_of_capital, 2)

        preferred_rate = float(params.get("preferred_return_rate", 0))
        preferred_months = float(params.get("preferred_return_months", 12))
        preferred_due = round(paid_in * preferred_rate * preferred_months / 12, 2)
        preferred_return = min(remaining, preferred_due)
        remaining = round(remaining - preferred_return, 2)

        gp_carry_rate = float(params.get("gp_carry", 0.2))
        gp_carry = round(max(remaining, 0) * gp_carry_rate, 2)
        lp_profit = round(max(remaining, 0) - gp_carry, 2)
        lp_distribution = round(return_of_capital + preferred_return + lp_profit, 2)

        return {
            "return_of_capital": round(return_of_capital, 2),
            "preferred_return": round(preferred_return, 2),
            "lp_profit_split": lp_profit,
            "gp_carry": gp_carry,
            "lp_distribution": lp_distribution,
            "total_distribution": round(amount, 2),
        }

    def _fund_terms_summary(self) -> dict[str, Any]:
        return {
            "lp_commitment": self._lp_commitment(),
            "management_fee": self._clause_parameters("management_fee"),
            "default_remedies": self._clause_parameters("default_remedies"),
            "reserve_account": self._clause_parameters("reserve_account"),
            "voting_threshold": self._clause_parameters("voting_threshold"),
            "waterfall_rule": self._clause_parameters("waterfall_rule"),
            "audit_review": self._clause_parameters("audit_review"),
        }

    def _reserve_requirement(self) -> float:
        params = self._clause_parameters("reserve_account")
        minimum_cash = float(params.get("minimum_cash", 0))
        rate_of_called = float(params.get("rate_of_called_capital", 0))
        called = float(self.state.funds[self.fund_id].get("called_capital", 0))
        return round(max(minimum_cash, called * rate_of_called), 2)

    def _default_remedy(self, called_amount: float) -> dict[str, Any]:
        params = self._clause_parameters("default_remedies")
        annual_rate = float(params.get("default_interest_annual_rate", 0.12))
        interest_days = int(params.get("default_interest_days", 30))
        return {
            "default_penalty": round(called_amount * annual_rate * interest_days / 365, 2),
            "default_interest_annual_rate": annual_rate,
            "default_interest_days": interest_days,
            "cure_period_days": int(params.get("cure_period_days", 15)),
            "voting_rights_suspended": bool(params.get("suspend_voting_rights", True)),
            "new_deployments_blocked": bool(params.get("block_new_deployments", True)),
        }

    def _audit_required_checks(self) -> list[str]:
        params = self._clause_parameters("audit_review")
        checks = params.get("required_checks", [])
        return checks if isinstance(checks, list) else []

    def _financial_plan(self) -> dict[str, Any]:
        return self.scenario.get("financial_plan") or {}

    def _follow_on_reserve_amount(self) -> float:
        financial_plan = self._financial_plan()
        if financial_plan.get("follow_on_reserve_amount") is not None:
            return round(float(financial_plan.get("follow_on_reserve_amount") or 0), 2)
        investment_amount = float(financial_plan.get("investment_amount") or 0)
        if investment_amount <= 0:
            investment_amount = sum(float(position.get("cost", 0) or 0) for position in self.state.portfolio_positions.values())
        if investment_amount <= 0:
            investment_amount = 750000.0
        return round(investment_amount * 0.20, 2)

    def _portfolio_nav(self) -> float:
        return round(
            sum(float(position.get("current_value", 0) or 0) for position in self.state.portfolio_positions.values()),
            2,
        )

    def _net_asset_value(self) -> float:
        return round(float(self.state.funds[self.fund_id].get("cash", 0) or 0) + self._portfolio_nav(), 2)

    def _record_nav_snapshot(self, simulation_time: str, label: str, event_type: str) -> None:
        self.state.lifecycle.setdefault("nav_snapshots", []).append({
            "simulation_time": simulation_time,
            "label": label,
            "event_type": event_type,
            "cash": round(float(self.state.funds[self.fund_id].get("cash", 0) or 0), 2),
            "portfolio_nav": self._portfolio_nav(),
            "net_asset_value": self._net_asset_value(),
            "evidence_refs": [f"event_log.jsonl#after_{event_type}_{simulation_time}"],
        })

    def _capital_call_schedule(self) -> list[dict[str, Any]]:
        return self.state.lifecycle.setdefault("capital_call_schedule", [])

    def _latest_open_capital_call(self) -> dict[str, Any] | None:
        for call in reversed(self._capital_call_schedule()):
            if call.get("status") in {"issued", "open"}:
                return call
        return None

    def _build_lifecycle_summary(self) -> dict[str, Any]:
        fund = self.state.funds[self.fund_id]
        lp = self.state.lps[self.lp_id]
        commitment = float(lp.get("commitment", 0) or 0)
        called = float(fund.get("called_capital", 0) or 0)
        paid = float(fund.get("paid_in_capital", 0) or 0)
        unfunded = float(fund.get("unfunded_commitments", 0) or 0)
        follow_on_target = self._follow_on_reserve_amount()
        reserve_required = self._reserve_requirement()
        available_after_reserve = round(max(float(fund.get("cash", 0) or 0) - reserve_required, 0), 2)
        follow_on_gap = round(max(follow_on_target - available_after_reserve, 0), 2)
        nav = self._net_asset_value()
        distributions = float(lp.get("distributions_received", 0) or 0)
        paid_in_multiple = round((nav + distributions) / paid, 4) if paid else 0
        resource_items = [
            {
                "item": "Subscription package and LP onboarding evidence",
                "status": "ready" if commitment > 0 else "missing",
                "owner": "GP",
                "evidence_refs": ["fund_terms.yaml#parties.lps"],
            },
            {
                "item": "Capital call wiring and notice process",
                "status": "ready" if called > 0 and paid > 0 else "needs_review",
                "owner": "GP Finance",
                "evidence_refs": ["event_log.jsonl#CapitalCallIssued", "ledger.jsonl#capital_contribution"],
            },
            {
                "item": "Follow-on reserve capacity for the next portfolio decision",
                "status": "ready" if follow_on_gap == 0 else "needs_lp_capital_or_distribution_holdback",
                "owner": "GP / IC",
                "evidence_refs": ["report_context.json#fund_lifecycle_summary.follow_on_reserve"],
            },
            {
                "item": "LP reporting cadence and NAV snapshot",
                "status": "ready" if self.state.lifecycle.get("nav_snapshots") else "missing",
                "owner": "GP Investor Relations",
                "evidence_refs": ["report_context.json#nav_snapshots"],
            },
        ]
        readiness_status = "ready_for_lp_discussion"
        if any(item["status"] in {"missing", "needs_review"} for item in resource_items):
            readiness_status = "needs_operational_cleanup"
        if any(item["status"] == "needs_lp_capital_or_distribution_holdback" for item in resource_items):
            readiness_status = "needs_lp_strategy_decision"
        return {
            "schema_version": "0.1",
            "focus": "lp_onboarding_capital_strategy",
            "commitment_summary": {
                "lp_id": self.lp_id,
                "lp_name": self.lp_name,
                "commitment": commitment,
                "called_capital": round(called, 2),
                "paid_in_capital": round(paid, 2),
                "unfunded_commitment": round(unfunded, 2),
                "called_percent_of_commitment": round(called / commitment, 4) if commitment else 0,
                "paid_percent_of_commitment": round(paid / commitment, 4) if commitment else 0,
            },
            "capital_call_rounds": len(self._capital_call_schedule()),
            "capital_call_schedule": self._capital_call_schedule(),
            "nav_summary": {
                "net_asset_value": nav,
                "portfolio_nav": self._portfolio_nav(),
                "cash": round(float(fund.get("cash", 0) or 0), 2),
                "distributions_to_lp": round(distributions, 2),
                "paid_in_multiple": paid_in_multiple,
            },
            "follow_on_reserve": {
                "target": follow_on_target,
                "available_after_required_reserve": available_after_reserve,
                "gap": follow_on_gap,
                "status": "funded" if follow_on_gap == 0 else "needs_top_up_or_holdback",
                "strategy": "Maintain reserve before the next follow-on or bridge financing decision.",
            },
            "lp_readiness_summary": {
                "status": readiness_status,
                "items": resource_items,
                "recommended_next_step": (
                    "Use the lifecycle summary in LP discussions to confirm capital call timing and follow-on reserve strategy."
                    if readiness_status == "ready_for_lp_discussion"
                    else "Resolve readiness gaps before treating the LP capital plan as executable."
                ),
            },
            "nav_snapshots": self.state.lifecycle.get("nav_snapshots", []),
        }

    def _binding(
        self,
        binding_id: str,
        target_path: str,
        target_type: str,
        source_ref: str,
        source_snippet: str,
        confidence: str,
        audit_trail: list[str],
        source_type: str = "deterministic_runtime",
    ) -> dict[str, Any]:
        return {
            "binding_id": binding_id,
            "target_path": target_path,
            "target_type": target_type,
            "source_type": source_type,
            "source_ref": source_ref,
            "source_snippet": source_snippet,
            "confidence": confidence,
            "commit_policy": "evidence_only_does_not_mutate_ledger",
            "audit_trail": audit_trail,
        }

    def _build_evidence_bindings(self, report_context: dict[str, Any], branch_results: dict[str, Any]) -> dict[str, Any]:
        bindings: list[dict[str, Any]] = []
        source_project = self.config.get("source_project", {})
        proposed_financial_plan = self.scenario.get("proposed_financial_plan", {})
        proposed_fund_terms = self.scenario.get("proposed_fund_terms", {})
        financial_hints = source_project.get("financial_hints", {})
        financial_sentences = financial_hints.get("sentences") or []
        fund_term_hints = source_project.get("fund_term_hints", {})
        fund_term_sentences = fund_term_hints.get("sentences") or []

        for key, proposal in proposed_financial_plan.get("proposals", {}).items():
            source_snippet = proposal.get("source_amount") or proposal.get("source_percentage") or (financial_sentences[0] if financial_sentences else "")
            bindings.append(self._binding(
                f"evidence_financial_plan_{key}",
                f"proposed_financial_plan.proposals.{key}",
                "financial_plan_proposal",
                "source_project.financial_hints",
                str(source_snippet),
                proposal.get("confidence", "unknown"),
                [
                    "project_extracted_text parsed into financial_hints",
                    "proposal remains non-authoritative until explicit financial-plan commit",
                ],
                "project_extracted_text",
            ))

        for key, proposal in proposed_fund_terms.get("proposals", {}).items():
            bindings.append(self._binding(
                f"evidence_fund_terms_{key}",
                f"proposed_fund_terms.proposals.{key}",
                "fund_term_proposal",
                "source_project.fund_term_hints",
                proposal.get("evidence") or (fund_term_sentences[0] if fund_term_sentences else ""),
                proposal.get("confidence", "unknown"),
                [
                    "project_extracted_text parsed into fund_term_hints",
                    "proposal remains non-authoritative until explicit fund-terms commit",
                ],
                "project_extracted_text",
            ))

        for key in ["management_fee", "reserve_account", "waterfall_rule", "default_remedies", "voting_threshold", "audit_review"]:
            bindings.append(self._binding(
                f"evidence_executable_terms_{key}",
                f"fund_terms_summary.{key}",
                "executable_fund_term",
                f"fund_terms.yaml#contracts.clauses.{key}",
                f"Executable {key} clause loaded from fund_terms.yaml.",
                "high",
                [
                    "fund_terms.yaml loaded by deterministic business simulation engine",
                    "clause values affect rule execution only through validated runtime handlers",
                ],
            ))

        lifecycle = report_context.get("fund_lifecycle_summary", {})
        commitment = lifecycle.get("commitment_summary", {})
        bindings.append(self._binding(
            "evidence_lifecycle_commitment",
            "fund_lifecycle_summary.commitment_summary",
            "lp_capital_lifecycle",
            "state_snapshot.json#funds/lps",
            (
                f"LP commitment {commitment.get('commitment', 0):,.2f}; "
                f"called {commitment.get('called_capital', 0):,.2f}; "
                f"unfunded {commitment.get('unfunded_commitment', 0):,.2f}."
            ),
            "high",
            [
                "capital calls validated against unfunded commitment",
                "LP payments posted through balanced ledger entries",
                "state_snapshot captures final paid-in and unfunded commitment",
            ],
        ))
        bindings.append(self._binding(
            "evidence_lifecycle_follow_on_reserve",
            "fund_lifecycle_summary.follow_on_reserve",
            "lp_capital_strategy",
            "event_log.jsonl#FollowOnReserveReview;event_log.jsonl#FollowOnCapitalCall",
            f"Follow-on reserve status is {(lifecycle.get('follow_on_reserve') or {}).get('status', 'unknown')}.",
            "high",
            [
                "FollowOnReserveReview computes reserve gap",
                "FollowOnCapitalCall tops up follow-on reserve without mutating extracted proposal hints",
            ],
        ))
        for index, call in enumerate(report_context.get("capital_call_schedule", []), start=1):
            bindings.append(self._binding(
                f"evidence_capital_call_round_{index}",
                f"capital_call_schedule[{index - 1}]",
                "capital_call",
                f"event_log.jsonl#CapitalCallIssued.{call.get('call_id', '')};ledger.jsonl#capital_contribution",
                (
                    f"Round {call.get('round')} {call.get('type')} call for "
                    f"{float(call.get('amount', 0) or 0):,.2f}, status {call.get('status')}."
                ),
                "high",
                [
                    "capital call amount checked against unfunded commitment",
                    "LP payment posted to ledger before schedule status is marked paid",
                ],
            ))
        for index, snapshot in enumerate(report_context.get("nav_snapshots", []), start=1):
            bindings.append(self._binding(
                f"evidence_nav_snapshot_{index}",
                f"nav_snapshots[{index - 1}]",
                "nav_snapshot",
                (snapshot.get("evidence_refs") or ["state_snapshot.json#lifecycle.nav_snapshots"])[0],
                f"{snapshot.get('label', 'NAV snapshot')}: NAV {float(snapshot.get('net_asset_value', 0) or 0):,.2f}.",
                "high",
                [
                    "NAV snapshot produced from deterministic cash plus portfolio NAV",
                    "snapshot is report evidence only and does not write ledger",
                ],
            ))

        for branch_id, branch in branch_results.get("branches", {}).items():
            profile = branch.get("governance") or {}
            bindings.append(self._binding(
                f"evidence_branch_risk_{branch_id}",
                f"branch_results.branches.{branch_id}.governance",
                "branch_risk",
                f"branch_results.json#branches.{branch_id}",
                branch.get("summary", ""),
                "medium",
                [
                    "branch risk score is computed from deterministic financial/state impacts",
                    "branch output is scenario comparison evidence and does not mutate base ledger",
                ],
            ))
            for term in profile.get("triggered_terms", []):
                bindings.append(self._binding(
                    f"evidence_branch_{branch_id}_term_{term}",
                    f"branch_results.branches.{branch_id}.governance.triggered_terms.{term}",
                    "triggered_governance_term",
                    f"fund_terms.yaml#contracts.clauses.{term}",
                    f"Branch {branch_id} triggered {term}.",
                    "medium",
                    [
                        "triggered term inferred from branch governance profile",
                        "review before using as legal conclusion",
                    ],
                ))

        bindings.append(self._binding(
            "evidence_report_context",
            "report_context",
            "report_artifact",
            "event_log.jsonl;ledger.jsonl;decision_records.jsonl;rule_execution_records.jsonl;state_snapshot.json",
            "Report context is assembled from event log, ledger, decisions, rule execution records, and state snapshot.",
            "high",
            [
                "runtime emits append-only logs",
                "report_context is generated after deterministic simulation completes",
            ],
        ))
        audit_trail = [
            {
                "step": "source_project_extraction",
                "summary": "Project extracted text is parsed into non-authoritative financial and fund-term hints.",
                "evidence_refs": ["source_project.financial_hints", "source_project.fund_term_hints"],
            },
            {
                "step": "deterministic_runtime",
                "summary": "BusinessSimulationEngine validates events, rules, ledger entries, and state transitions.",
                "evidence_refs": ["event_log.jsonl", "ledger.jsonl", "rule_execution_records.jsonl", "state_snapshot.json"],
            },
            {
                "step": "evidence_binding",
                "summary": "Evidence bindings connect report, lifecycle, branch, and governance outputs back to source snippets and runtime artifacts.",
                "evidence_refs": ["evidence_bindings.json"],
            },
        ]
        return {
            "schema_version": "0.1",
            "binding_policy": "evidence_only_does_not_mutate_ledger",
            "source_project_id": source_project.get("project_id", ""),
            "bindings_count": len(bindings),
            "bindings": bindings,
            "audit_trail": audit_trail,
        }

    def _resolve_input(self, key: str) -> Path:
        path = Path(self.config["input_paths"][key])
        return path if path.is_absolute() else self.base_dir / path

    def _resolve_output(self, path_text: str) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else self.base_dir / path

    def _initial_state(self, simulation_id: str, scenario_id: str) -> RuntimeState:
        fund = self.fund_terms["fund"]
        lp = self.fund_terms["parties"]["lps"][0]
        return RuntimeState(
            simulation_id=simulation_id,
            scenario_id=scenario_id,
            funds={
                fund["id"]: {
                    "name": fund["name"],
                    "status": "draft",
                    "currency": fund.get("currency", "USD"),
                    "called_capital": 0.0,
                    "paid_in_capital": 0.0,
                    "unfunded_commitments": float(lp["commitment"]),
                    "cash": 0.0,
                    "nav": 0.0,
                }
            },
            lps={
                lp["id"]: {
                    "name": lp["name"],
                    "commitment": float(lp["commitment"]),
                    "paid_in": 0.0,
                    "default_status": "none",
                    "penalties_accrued": 0.0,
                    "distributions_received": 0.0,
                }
            },
            lifecycle={
                "capital_call_schedule": [],
                "nav_snapshots": [],
            },
        )

    def run(self) -> RunResult:
        self._write_run_state("running")
        write_json(
            self.compiled_world_path,
            {
                "schema_version": "0.1",
                "simulation_id": self.config["simulation_id"],
                "engine_type": "business_governance",
                "fund_id": self.fund_id,
                "fund_name": self.fund_name,
                "scenario_id": self.scenario["scenario"]["id"],
                "agents_count": len(self.agent_profiles.get("agents", [])),
                "contracts_count": len(self.fund_terms.get("contracts", [])),
                "source_project": self.config.get("source_project", {}),
            },
        )
        for initial in self.scenario["initial_events"]:
            self._schedule(initial)

        for event in self._planned_events():
            self._schedule(event)

        while self.queue:
            _, _, item = heapq.heappop(self.queue)
            self._apply_event(item["event_type"], item["simulation_time"], item.get("payload", {}))

        self.state.completed_at = datetime.now().isoformat()
        self._finalize_ledger_summary()
        self.state.lifecycle["fund_lifecycle_summary"] = self._build_lifecycle_summary()
        branch_results = self._simulate_branch_results()
        write_json(self.branch_results_path, branch_results)
        write_json(self.state_path, self.state.model_dump(mode="json"))
        report_context = assemble_report_context(
            self.state,
            self.events,
            self.ledger_entries,
            self._branch_summaries(branch_results),
            branch_results,
        )
        report_context["source_project"] = self.config.get("source_project", {})
        report_context["object_name_map"] = self._object_name_map()
        report_context["event_plan_summary"] = self._event_plan_summary()
        report_context["financial_plan"] = self.scenario.get("financial_plan", {})
        report_context["proposed_financial_plan"] = self.scenario.get("proposed_financial_plan", {})
        report_context["proposed_fund_terms"] = self.scenario.get("proposed_fund_terms", {})
        report_context["manual_scenario_patch"] = self.scenario.get("manual_scenario_patch", {})
        report_context["fund_lifecycle_summary"] = self.state.lifecycle.get("fund_lifecycle_summary", {})
        report_context["capital_call_schedule"] = self.state.lifecycle.get("capital_call_schedule", [])
        report_context["nav_snapshots"] = self.state.lifecycle.get("nav_snapshots", [])
        report_context["lp_readiness_summary"] = (
            self.state.lifecycle.get("fund_lifecycle_summary", {}).get("lp_readiness_summary", {})
        )
        revision_path = self.base_dir / "scenario_revisions.json"
        if revision_path.exists():
            revision_ledger = load_structured_file(revision_path)
            report_context["scenario_revision"] = {
                "current_revision_id": revision_ledger.get("current_revision_id", ""),
                "revisions_count": len(revision_ledger.get("revisions", [])),
                "latest_revision": (revision_ledger.get("revisions") or [{}])[-1],
            }
        report_context["fund_terms_summary"] = self._fund_terms_summary()
        evidence_bindings = self._build_evidence_bindings(report_context, branch_results)
        report_context["evidence_bindings"] = evidence_bindings
        report_context["evidence_audit_trail"] = evidence_bindings.get("audit_trail", [])
        write_json(self.evidence_bindings_path, evidence_bindings)
        write_json(self.report_context_path, report_context)
        self._write_run_state("completed")
        return RunResult(
            state=self.state,
            event_count=len(self.events),
            ledger_entry_count=len(self.ledger_entries),
            decision_count=len(self.decisions),
            rule_execution_count=len(self.rule_records),
        )

    def _schedule_many(self, events: list[tuple[str, str, dict[str, Any]]]) -> None:
        for simulation_time, event_type, payload in events:
            self._schedule({"simulation_time": simulation_time, "event_type": event_type, "payload": payload})

    def _planned_events(self) -> list[dict[str, Any]]:
        configured = self.scenario.get("planned_events")
        if configured:
            return self._with_lifecycle_events(list(configured))
        return self._with_lifecycle_events([
            {"simulation_time": "2026-02-15", "event_type": "DealEvaluation", "payload": {"deal_id": f"deal_{self.portfolio_company_id}", "portfolio_company_id": self.portfolio_company_id}},
            {"simulation_time": "2026-02-20", "event_type": "ComplianceCheck", "payload": {"deal_id": f"deal_{self.portfolio_company_id}"}},
            {"simulation_time": "2026-03-01", "event_type": "ICMeeting", "payload": {"deal_id": f"deal_{self.portfolio_company_id}"}},
            {"simulation_time": "2026-03-05", "event_type": "ManagementFeePayment", "payload": {"period": "Q1"}},
            {"simulation_time": "2026-03-10", "event_type": "InvestmentExecution", "payload": {"deal_id": f"deal_{self.portfolio_company_id}", "amount": 750000}},
            {"simulation_time": "2026-04-15", "event_type": "QuarterlyReport", "payload": {"quarter": "Q1"}},
            {"simulation_time": "2026-07-15", "event_type": "QuarterlyReport", "payload": {"quarter": "Q2"}},
            {"simulation_time": "2026-08-01", "event_type": "FollowOnDiscussion", "payload": {"portfolio_company_id": self.portfolio_company_id}},
            {"simulation_time": "2026-08-05", "event_type": "FollowOnReserveReview", "payload": {"portfolio_company_id": self.portfolio_company_id}},
            {"simulation_time": "2026-10-01", "event_type": "LiquidityEvent", "payload": {"portfolio_company_id": self.portfolio_company_id, "proceeds": 1200000}},
            {"simulation_time": "2026-10-03", "event_type": "ReserveAccountReview", "payload": {}},
            {"simulation_time": "2026-10-05", "event_type": "Distribution", "payload": {"amount": 1150000}},
            {"simulation_time": "2026-11-01", "event_type": "FollowOnCapitalCall", "payload": {"purpose": "follow_on_reserve_top_up"}},
            {"simulation_time": "2026-12-15", "event_type": "AuditReview", "payload": {}},
        ])

    def _with_lifecycle_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        event_types = {event.get("event_type") for event in events}
        additions: list[dict[str, Any]] = []
        if "FollowOnReserveReview" not in event_types:
            additions.append({
                "simulation_time": "2026-08-05",
                "event_type": "FollowOnReserveReview",
                "payload": {
                    "portfolio_company_id": self.portfolio_company_id,
                    "target_reserve": self._follow_on_reserve_amount(),
                    "generated_from": "m3_lifecycle_augmentation",
                },
            })
        if "FollowOnCapitalCall" not in event_types:
            additions.append({
                "simulation_time": "2026-11-01",
                "event_type": "FollowOnCapitalCall",
                "payload": {
                    "amount": self._follow_on_reserve_amount(),
                    "purpose": "follow_on_reserve_top_up",
                    "generated_from": "m3_lifecycle_augmentation",
                },
            })
        if not additions:
            return events
        return sorted([*events, *additions], key=lambda item: item.get("simulation_time", ""))

    def _schedule(self, event: dict[str, Any]) -> None:
        self.sequence += 1
        heapq.heappush(self.queue, (event["simulation_time"], self.sequence, event))

    def _apply_event(self, event_type: str, simulation_time: str, payload: dict[str, Any]) -> None:
        handler = getattr(self, f"_handle_{event_type}", self._handle_generic)
        handler(simulation_time, payload)

    def _emit_event(
        self,
        simulation_time: str,
        event_type: str,
        payload: dict[str, Any],
        touched_objects: list[ObjectRef],
        actor_agents: list[str] | None = None,
        decision_refs: list[str] | None = None,
        rule_refs: list[str] | None = None,
        ledger_refs: list[str] | None = None,
    ) -> BusinessEvent:
        self.state.current_event_index += 1
        event = BusinessEvent(
            event_id=f"evt_{self.state.current_event_index:04d}",
            timestamp=datetime.now().isoformat(),
            simulation_time=simulation_time,
            scenario_id=self.state.scenario_id,
            branch_id=self.state.branch_id,
            event_type=event_type,
            actor_agents=actor_agents or ["agent_gp"],
            touched_objects=touched_objects,
            payload=payload,
            source=EventSource(evidence_refs=payload.get("evidence_refs", [])),
            decision_record_refs=decision_refs or [],
            rule_execution_refs=rule_refs or [],
            ledger_entry_refs=ledger_refs or [],
        )
        self.events.append(event)
        self.event_writer.write(event)
        return event

    def _rule(self, simulation_time: str, event_id: str, rule_id: str, inputs: dict, output: dict, passed: bool = True) -> str:
        record = RuleExecutionRecord(
            rule_execution_id=f"rule_exec_{len(self.rule_records) + 1:04d}",
            timestamp=datetime.now().isoformat(),
            simulation_time=simulation_time,
            event_id=event_id,
            rule_id=rule_id,
            inputs=inputs,
            output=output,
            passed=passed,
        )
        self.rule_records.append(record)
        self.rule_writer.write(record)
        return record.rule_execution_id

    def _decision(self, simulation_time: str, event_id: str, decision_type: str, result: str, rationale: str) -> str:
        record = DecisionRecord(
            decision_record_id=f"decision_{len(self.decisions) + 1:04d}",
            timestamp=datetime.now().isoformat(),
            simulation_time=simulation_time,
            event_id=event_id,
            decision_type=decision_type,
            authority="IC",
            result=result,
            rationale=rationale,
        )
        self.decisions.append(record)
        self.state.decisions[record.decision_record_id] = record.model_dump(mode="json")
        self.decision_writer.write(record)
        return record.decision_record_id

    def _ledger(self, simulation_time: str, event_id: str, description: str, lines: list[LedgerLine]) -> str:
        entry = LedgerEntry(
            ledger_entry_id=f"ledger_{len(self.ledger_entries) + 1:04d}",
            timestamp=datetime.now().isoformat(),
            simulation_time=simulation_time,
            event_id=event_id,
            description=description,
            lines=lines,
        )
        if not entry.balanced:
            raise ValueError(f"Unbalanced ledger entry: {entry.ledger_entry_id}")
        self.ledger_entries.append(entry)
        self.ledger_writer.write(entry)
        return entry.ledger_entry_id

    def _handle_FundClosing(self, simulation_time: str, payload: dict[str, Any]) -> None:
        fund_id = self.fund_id
        self.state.funds[fund_id]["status"] = "active"
        self._emit_event(
            simulation_time,
            "FundClosing",
            {"fund_id": fund_id, "summary": f"{self.fund_name} closed and became active."},
            [ObjectRef(object_type="Fund", object_id=fund_id, qualifier="fund")],
        )

    def _handle_InitialCapitalCall(self, simulation_time: str, payload: dict[str, Any]) -> None:
        fund_id = payload["fund_id"]
        lp_id = payload["lp_id"]
        amount = float(payload["amount"])
        fund = self.state.funds[fund_id]
        lp = self.state.lps[lp_id]
        if amount > fund["unfunded_commitments"]:
            raise ValueError("Capital call exceeds unfunded commitment")
        fund["called_capital"] += amount
        fund["unfunded_commitments"] -= amount
        call_id = payload.get("call_id") or f"call_{len(self._capital_call_schedule()) + 1:03d}"
        obligation_id = f"obl_{call_id}"
        due_date = payload.get("due_date", "2026-01-30")
        purpose = payload.get("purpose", "initial_deployment")
        self.state.obligations[obligation_id] = {
            "type": "capital_call_payment",
            "owner": lp_id,
            "amount": amount,
            "status": "open",
            "due_date": due_date,
        }
        call_round = len(self._capital_call_schedule()) + 1
        self._capital_call_schedule().append({
            "call_id": call_id,
            "round": call_round,
            "type": "initial",
            "purpose": purpose,
            "notice_date": simulation_time,
            "due_date": due_date,
            "amount": amount,
            "status": "issued",
            "paid_amount": 0.0,
            "unfunded_commitment_after_call": round(float(fund["unfunded_commitments"]), 2),
            "evidence_refs": [f"event_log.jsonl#CapitalCallIssued.{call_id}"],
        })
        event = self._emit_event(
            simulation_time,
            "CapitalCallIssued",
            {
                "fund_id": fund_id,
                "lp_id": lp_id,
                "call_id": call_id,
                "round": call_round,
                "amount": amount,
                "purpose": purpose,
                "due_date": due_date,
                "summary": f"{self.gp_name} issued round {call_round} capital call of {amount:,.2f} to {lp['name']}.",
            },
            [
                ObjectRef(object_type="Fund", object_id=fund_id, qualifier="fund"),
                ObjectRef(object_type="LP", object_id=lp_id, qualifier="recipient"),
                ObjectRef(object_type="Contract", object_id="lpa_fund_i", qualifier="authority"),
            ],
        )
        rule_id = self._rule(simulation_time, event.event_id, "capital_call_within_unfunded_commitment", {"amount": amount}, {"passed": True})
        event.rule_execution_refs.append(rule_id)
        self._schedule({
            "simulation_time": payload.get("payment_date", "2026-01-25"),
            "event_type": "LPPaymentReceived",
            "payload": {"fund_id": fund_id, "lp_id": lp_id, "amount": amount, "call_id": call_id},
        })

    def _handle_LPPaymentReceived(self, simulation_time: str, payload: dict[str, Any]) -> None:
        fund_id = payload["fund_id"]
        lp_id = payload["lp_id"]
        amount = float(payload["amount"])
        self.state.funds[fund_id]["paid_in_capital"] += amount
        self.state.funds[fund_id]["cash"] += amount
        self.state.lps[lp_id]["paid_in"] += amount
        call = next(
            (item for item in self._capital_call_schedule() if item.get("call_id") == payload.get("call_id")),
            self._latest_open_capital_call(),
        )
        call_id = call.get("call_id") if call else payload.get("call_id", "call_001")
        obligation_id = f"obl_{call_id}"
        if obligation_id in self.state.obligations:
            self.state.obligations[obligation_id]["status"] = "fulfilled"
        if call:
            call["status"] = "paid"
            call["paid_amount"] = round(float(call.get("paid_amount", 0) or 0) + amount, 2)
            call["paid_at"] = simulation_time
            call["cash_after_payment"] = round(float(self.state.funds[fund_id]["cash"]), 2)
        event = self._emit_event(
            simulation_time,
            "LPPaymentReceived",
            {
                "fund_id": fund_id,
                "lp_id": lp_id,
                "call_id": call_id,
                "amount": amount,
                "summary": f"{self.lp_name} paid {amount:,.2f} for {call_id} before the due date.",
            },
            [ObjectRef(object_type="Fund", object_id=fund_id), ObjectRef(object_type="LP", object_id=lp_id)],
            actor_agents=["agent_lp_a"],
        )
        ledger_id = self._ledger(
            simulation_time,
            event.event_id,
            "LP capital contribution received",
            [
                LedgerLine(account="cash", debit=amount, object_id=fund_id),
                LedgerLine(account="capital_contribution", credit=amount, object_id=lp_id),
            ],
        )
        event.ledger_entry_refs.append(ledger_id)
        self._record_nav_snapshot(simulation_time, f"After {call_id} payment", "LPPaymentReceived")

    def _handle_DealEvaluation(self, simulation_time: str, payload: dict[str, Any]) -> None:
        self._emit_event(
            simulation_time,
            "DealEvaluation",
            {"summary": f"{self.gp_name} evaluated {self.portfolio_company_name} as a candidate investment.", **payload},
            [ObjectRef(object_type="PortfolioCompany", object_id=self.portfolio_company_id), ObjectRef(object_type="Fund", object_id=self.fund_id)],
        )

    def _handle_ComplianceCheck(self, simulation_time: str, payload: dict[str, Any]) -> None:
        self._emit_event(
            simulation_time,
            "ComplianceCheck",
            {"summary": f"Compliance check passed for {self.portfolio_company_name}.", "result": "passed", **payload},
            [ObjectRef(object_type="Regulator", object_id="regulator"), ObjectRef(object_type="PortfolioCompany", object_id=self.portfolio_company_id)],
        )

    def _handle_ICMeeting(self, simulation_time: str, payload: dict[str, Any]) -> None:
        threshold = self._ic_threshold_percent()
        approval_votes = float(payload.get("approval_votes_percent", 75))
        approved = approval_votes >= threshold
        event = self._emit_event(
            simulation_time,
            "ICMeeting",
            {
                "summary": f"IC met and approved the {self.portfolio_company_name} investment.",
                "approval_votes_percent": approval_votes,
                "approval_threshold_percent": threshold,
                **payload,
            },
            [ObjectRef(object_type="IC", object_id="ic"), ObjectRef(object_type="PortfolioCompany", object_id=self.portfolio_company_id)],
        )
        rule_id = self._rule(
            simulation_time,
            event.event_id,
            "ic_approval_threshold_met",
            {"approval_votes_percent": approval_votes, "threshold_percent": threshold},
            {"approved": approved},
            approved,
        )
        event.rule_execution_refs.append(rule_id)
        decision_result = "approved" if approved else "rejected"
        rationale = f"{approval_votes:.2f}% approval {'met' if approved else 'missed'} the {threshold:.2f}% threshold."
        decision_id = self._decision(simulation_time, event.event_id, "investment_approval", decision_result, rationale)
        event.decision_record_refs.append(decision_id)

    def _handle_ManagementFeePayment(self, simulation_time: str, payload: dict[str, Any]) -> None:
        amount = float(payload.get("amount") or self._management_fee_amount())
        if amount <= 0:
            self._emit_event(
                simulation_time,
                "ManagementFeePayment",
                {"summary": "No management fee was due for this period.", **payload},
                [ObjectRef(object_type="Fund", object_id=self.fund_id), ObjectRef(object_type="GP", object_id=self.gp_id)],
            )
            return

        self.state.funds[self.fund_id]["cash"] -= amount
        self.state.funds[self.fund_id]["management_fees_paid"] = self.state.funds[self.fund_id].get("management_fees_paid", 0) + amount
        event = self._emit_event(
            simulation_time,
            "ManagementFeePayment",
            {"summary": f"{self.fund_name} paid {amount:,.2f} management fee to {self.gp_name}.", "amount": amount, **payload},
            [ObjectRef(object_type="Fund", object_id=self.fund_id), ObjectRef(object_type="GP", object_id=self.gp_id), ObjectRef(object_type="Contract", object_id="lpa_fund_i")],
        )
        ledger_id = self._ledger(
            simulation_time,
            event.event_id,
            "Management fee paid",
            [
                LedgerLine(account="management_fee_expense", debit=amount, object_id=self.fund_id),
                LedgerLine(account="cash", credit=amount, object_id=self.fund_id),
            ],
        )
        event.ledger_entry_refs.append(ledger_id)

    def _handle_InvestmentExecution(self, simulation_time: str, payload: dict[str, Any]) -> None:
        fund_id = self.fund_id
        portfolio_company_id = self.portfolio_company_id
        amount = float(payload["amount"])
        self.state.funds[fund_id]["cash"] -= amount
        self.state.funds[fund_id]["nav"] += amount
        position_id = f"pos_{portfolio_company_id}"
        self.state.portfolio_positions[position_id] = {
            "portfolio_company_id": portfolio_company_id,
            "cost": amount,
            "current_value": amount,
            "status": "active",
        }
        event = self._emit_event(
            simulation_time,
            "InvestmentExecution",
            {"summary": f"{self.fund_name} invested {amount:,.2f} in {self.portfolio_company_name}.", **payload},
            [ObjectRef(object_type="Fund", object_id=fund_id), ObjectRef(object_type="PortfolioCompany", object_id=portfolio_company_id)],
        )
        ledger_id = self._ledger(
            simulation_time,
            event.event_id,
            "Investment funded",
            [
                LedgerLine(account="investment_asset", debit=amount, object_id=portfolio_company_id),
                LedgerLine(account="cash", credit=amount, object_id=fund_id),
            ],
        )
        event.ledger_entry_refs.append(ledger_id)
        self._record_nav_snapshot(simulation_time, "Post-investment NAV", "InvestmentExecution")

    def _handle_QuarterlyReport(self, simulation_time: str, payload: dict[str, Any]) -> None:
        quarter = payload["quarter"]
        self._record_nav_snapshot(simulation_time, f"{quarter} NAV report", "QuarterlyReport")
        self._emit_event(
            simulation_time,
            "QuarterlyReport",
            {
                "summary": f"{self.gp_name} delivered {quarter} quarterly report to {self.lp_name}.",
                "net_asset_value": self._net_asset_value(),
                "portfolio_nav": self._portfolio_nav(),
                **payload,
            },
            [ObjectRef(object_type="Fund", object_id=self.fund_id), ObjectRef(object_type="LP", object_id=self.lp_id)],
        )

    def _handle_FollowOnDiscussion(self, simulation_time: str, payload: dict[str, Any]) -> None:
        self._emit_event(
            simulation_time,
            "FollowOnDiscussion",
            {"summary": f"{self.gp_name} and IC discussed follow-on reserves for {self.portfolio_company_name}.", **payload},
            [ObjectRef(object_type="GP", object_id=self.gp_id), ObjectRef(object_type="IC", object_id="ic"), ObjectRef(object_type="PortfolioCompany", object_id=self.portfolio_company_id)],
        )

    def _handle_FollowOnReserveReview(self, simulation_time: str, payload: dict[str, Any]) -> None:
        target = round(float(payload.get("target_reserve") or self._follow_on_reserve_amount()), 2)
        required_reserve = self._reserve_requirement()
        cash = round(float(self.state.funds[self.fund_id].get("cash", 0) or 0), 2)
        available_after_reserve = round(max(cash - required_reserve, 0), 2)
        gap = round(max(target - available_after_reserve, 0), 2)
        status = "ready" if gap == 0 else "needs_follow_on_top_up"
        self.state.lifecycle["follow_on_reserve_review"] = {
            "simulation_time": simulation_time,
            "portfolio_company_id": payload.get("portfolio_company_id", self.portfolio_company_id),
            "target": target,
            "cash": cash,
            "required_reserve": required_reserve,
            "available_after_required_reserve": available_after_reserve,
            "gap": gap,
            "status": status,
        }
        event = self._emit_event(
            simulation_time,
            "FollowOnReserveReview",
            {
                "summary": (
                    f"{self.gp_name} reviewed {target:,.2f} follow-on reserve target for "
                    f"{self.portfolio_company_name}; gap is {gap:,.2f}."
                ),
                "target_reserve": target,
                "available_after_required_reserve": available_after_reserve,
                "gap": gap,
                "status": status,
                **payload,
            },
            [
                ObjectRef(object_type="Fund", object_id=self.fund_id),
                ObjectRef(object_type="PortfolioCompany", object_id=self.portfolio_company_id),
                ObjectRef(object_type="LP", object_id=self.lp_id),
            ],
        )
        rule_id = self._rule(
            simulation_time,
            event.event_id,
            "follow_on_reserve_capacity_reviewed",
            {"target_reserve": target, "available_after_required_reserve": available_after_reserve},
            {"gap": gap, "status": status},
            True,
        )
        event.rule_execution_refs.append(rule_id)

    def _handle_FollowOnCapitalCall(self, simulation_time: str, payload: dict[str, Any]) -> None:
        review = self.state.lifecycle.get("follow_on_reserve_review", {})
        amount = round(float(payload.get("amount") or review.get("gap") or self._follow_on_reserve_amount()), 2)
        if amount <= 0:
            self._emit_event(
                simulation_time,
                "FollowOnCapitalCall",
                {
                    "summary": "No follow-on capital call was required because reserve capacity was sufficient.",
                    "amount": amount,
                    **payload,
                },
                [ObjectRef(object_type="Fund", object_id=self.fund_id), ObjectRef(object_type="LP", object_id=self.lp_id)],
            )
            return
        self._handle_InitialCapitalCall(
            simulation_time,
            {
                "fund_id": self.fund_id,
                "lp_id": self.lp_id,
                "amount": amount,
                "call_id": payload.get("call_id", f"call_{len(self._capital_call_schedule()) + 1:03d}"),
                "due_date": payload.get("due_date", "2026-11-15"),
                "payment_date": payload.get("payment_date", "2026-11-10"),
                "purpose": payload.get("purpose", "follow_on_reserve_top_up"),
            },
        )
        last_call = self._capital_call_schedule()[-1]
        last_call["type"] = "follow_on"
        last_call["resource_strategy"] = "Prepare next-round capital availability for LP and IC discussions."

    def _handle_LiquidityEvent(self, simulation_time: str, payload: dict[str, Any]) -> None:
        proceeds = float(payload["proceeds"])
        position_id = f"pos_{self.portfolio_company_id}"
        position_cost = self.state.portfolio_positions[position_id]["cost"]
        self.state.funds[self.fund_id]["cash"] += proceeds
        self.state.funds[self.fund_id]["nav"] = max(0, self.state.funds[self.fund_id]["nav"] - position_cost)
        self.state.portfolio_positions[position_id]["status"] = "realized"
        self.state.portfolio_positions[position_id]["current_value"] = 0.0
        event = self._emit_event(
            simulation_time,
            "LiquidityEvent",
            {"summary": f"{self.portfolio_company_name} generated liquidity proceeds of {proceeds:,.2f}.", **payload},
            [ObjectRef(object_type="PortfolioCompany", object_id=self.portfolio_company_id), ObjectRef(object_type="Fund", object_id=self.fund_id)],
        )
        ledger_id = self._ledger(
            simulation_time,
            event.event_id,
            "Liquidity proceeds received",
            [
                LedgerLine(account="cash", debit=proceeds, object_id=self.fund_id),
                LedgerLine(account="investment_realization", credit=proceeds, object_id=self.portfolio_company_id),
            ],
        )
        event.ledger_entry_refs.append(ledger_id)
        self._record_nav_snapshot(simulation_time, "Post-liquidity NAV", "LiquidityEvent")

    def _handle_ReserveAccountReview(self, simulation_time: str, payload: dict[str, Any]) -> None:
        financial_plan = self.scenario.get("financial_plan", {})
        planned_distribution = float(payload.get("planned_distribution") or financial_plan.get("distribution_amount", 1150000.0))
        current_cash = float(self.state.funds[self.fund_id].get("cash", 0))
        projected_cash_after_distribution = round(current_cash - planned_distribution, 2)
        required_reserve = self._reserve_requirement()
        shortfall = round(max(required_reserve - projected_cash_after_distribution, 0), 2)
        passed = shortfall == 0
        self.state.funds[self.fund_id]["reserve_required"] = required_reserve
        self.state.funds[self.fund_id]["reserve_projected_after_distribution"] = projected_cash_after_distribution
        self.state.funds[self.fund_id]["reserve_shortfall"] = shortfall
        self.state.funds[self.fund_id]["reserve_compliant"] = passed
        event = self._emit_event(
            simulation_time,
            "ReserveAccountReview",
            {
                "summary": (
                    f"Reserve review projected {projected_cash_after_distribution:,.2f} cash after distribution "
                    f"against {required_reserve:,.2f} required reserve."
                ),
                "planned_distribution": planned_distribution,
                "projected_cash_after_distribution": projected_cash_after_distribution,
                "required_reserve": required_reserve,
                "shortfall": shortfall,
                **payload,
            },
            [ObjectRef(object_type="Fund", object_id=self.fund_id), ObjectRef(object_type="Contract", object_id="lpa_fund_i")],
        )
        rule_id = self._rule(
            simulation_time,
            event.event_id,
            "reserve_account_sufficient",
            {
                "projected_cash_after_distribution": projected_cash_after_distribution,
                "required_reserve": required_reserve,
            },
            {"shortfall": shortfall, "passed": passed},
            passed,
        )
        event.rule_execution_refs.append(rule_id)

    def _handle_Distribution(self, simulation_time: str, payload: dict[str, Any]) -> None:
        amount = float(payload["amount"])
        waterfall = self._waterfall(amount)
        lp_amount = waterfall["lp_distribution"]
        gp_carry = waterfall["gp_carry"]
        self.state.funds[self.fund_id]["cash"] -= amount
        self.state.lps[self.lp_id]["distributions_received"] += lp_amount
        self.state.funds[self.fund_id]["carry_allocated"] = self.state.funds[self.fund_id].get("carry_allocated", 0) + gp_carry
        event = self._emit_event(
            simulation_time,
            "Distribution",
            {
                "summary": f"{self.fund_name} distributed {lp_amount:,.2f} to {self.lp_name} and allocated {gp_carry:,.2f} carry to {self.gp_name}.",
                "lp_distribution": lp_amount,
                "gp_carry": gp_carry,
                "waterfall": waterfall,
                **payload,
            },
            [ObjectRef(object_type="Fund", object_id=self.fund_id), ObjectRef(object_type="LP", object_id=self.lp_id), ObjectRef(object_type="GP", object_id=self.gp_id)],
        )
        rule_id = self._rule(
            simulation_time,
            event.event_id,
            "waterfall_rule_applied",
            {"amount": amount, "paid_in": self.state.lps[self.lp_id].get("paid_in", 0)},
            waterfall,
            True,
        )
        ledger_id = self._ledger(
            simulation_time,
            event.event_id,
            "Distribution waterfall applied",
            [
                LedgerLine(account="distribution_expense", debit=amount, object_id=self.fund_id),
                LedgerLine(account="cash", credit=amount, object_id=self.fund_id),
            ],
        )
        event.rule_execution_refs.append(rule_id)
        event.ledger_entry_refs.append(ledger_id)
        self._record_nav_snapshot(simulation_time, "Post-distribution NAV", "Distribution")

    def _handle_AuditReview(self, simulation_time: str, payload: dict[str, Any]) -> None:
        self._finalize_ledger_summary()
        required_checks = self._audit_required_checks()
        check_results = {
            "ledger_balanced": self.state.ledger_summary.get("balanced", False),
            "reserve_account_reviewed": "reserve_compliant" in self.state.funds[self.fund_id],
            "waterfall_rule_applied": any(record.rule_id == "waterfall_rule_applied" for record in self.rule_records),
        }
        audit_exceptions = [
            {"check": check, "severity": "material", "message": f"Required audit check failed: {check}"}
            for check in required_checks
            if not check_results.get(check, False)
        ]
        self.state.funds[self.fund_id]["audit_exceptions_count"] = len(audit_exceptions)
        self._emit_event(
            simulation_time,
            "AuditReview",
            {
                "summary": (
                    f"Auditor reviewed event log, reserve policy, waterfall, and ledger. "
                    f"Ledger balanced: {self.state.ledger_summary['balanced']}. "
                    f"Exceptions: {len(audit_exceptions)}."
                ),
                "required_checks": required_checks,
                "check_results": check_results,
                "audit_exceptions": audit_exceptions,
                **payload,
            },
            [ObjectRef(object_type="Auditor", object_id="auditor"), ObjectRef(object_type="Fund", object_id=self.fund_id)],
        )

    def _handle_generic(self, simulation_time: str, payload: dict[str, Any]) -> None:
        self._emit_event(simulation_time, payload.get("event_type", "GenericEvent"), payload, [])

    def _finalize_ledger_summary(self) -> None:
        debit = sum(line.debit for entry in self.ledger_entries for line in entry.lines)
        credit = sum(line.credit for entry in self.ledger_entries for line in entry.lines)
        self.state.ledger_summary = {
            "debits": round(debit, 2),
            "credits": round(credit, 2),
            "balanced": round(debit - credit, 2) == 0,
            "entries": len(self.ledger_entries),
        }

    def _risk_level(self, score: int) -> str:
        if score >= 80:
            return "critical"
        if score >= 55:
            return "high"
        if score >= 30:
            return "medium"
        return "low"

    def _branch_governance_profile(
        self,
        branch_id: str,
        financial_impact: dict[str, Any],
        state_impact: dict[str, Any],
        triggered_terms: list[str],
        actions: list[str],
    ) -> dict[str, Any]:
        score = 10
        audit_flags: list[dict[str, Any]] = []

        if financial_impact.get("capital_paid", 0) < financial_impact.get("capital_called", 0):
            score += 35
            audit_flags.append({
                "severity": "high",
                "message": "Capital call was not fully paid.",
            })
        if state_impact.get("lp_default_status") == "defaulted":
            score += 30
        if state_impact.get("new_deployments") == "blocked":
            score += 15
        if state_impact.get("deployment_delay") or financial_impact.get("delay_days", 0):
            score += 20
        if financial_impact.get("delay_months", 0):
            score += 20
        valuation_change = float(financial_impact.get("valuation_change_percent", 0) or 0)
        if valuation_change <= -0.20:
            score += 20
            audit_flags.append({
                "severity": "medium",
                "message": f"Portfolio valuation changed by {valuation_change:.0%}; NAV support should be refreshed.",
            })
        nav_impairment = float(financial_impact.get("nav_impairment", 0) or 0)
        if nav_impairment > 0:
            score += 30
            audit_flags.append({
                "severity": "high",
                "message": f"NAV impairment of {nav_impairment:,.2f} requires IC and LP reporting review.",
            })
        if financial_impact.get("bridge_amount", 0):
            score += 15
        if state_impact.get("regulatory_status") == "blocked":
            score += 35
            audit_flags.append({
                "severity": "high",
                "message": "Regulatory block prevents execution or exit until clearance is obtained.",
            })
        if state_impact.get("write_off_status") == "full_write_off":
            score += 25
        if state_impact.get("lp_default_status") in {"cured", "waived"}:
            score += 10
        reserve_shortfall = float(financial_impact.get("reserve_shortfall", 0) or 0)
        if reserve_shortfall > 0:
            score += 25
            audit_flags.append({
                "severity": "medium",
                "message": f"Reserve shortfall of {reserve_shortfall:,.2f} should be reviewed before distribution.",
            })
        audit_exceptions = int(state_impact.get("audit_exceptions", 0) or 0)
        if audit_exceptions:
            score += min(30, audit_exceptions * 10)
        if state_impact.get("deal_status") == "rejected":
            score += 15

        score = min(score, 100)
        return {
            "risk_score": score,
            "risk_level": self._risk_level(score),
            "triggered_terms": triggered_terms,
            "governance_actions": actions,
            "audit_flags": audit_flags,
        }

    def _simulate_branch_results(self) -> dict[str, Any]:
        called = self.state.funds[self.fund_id]["called_capital"]
        investment_amount = self.state.portfolio_positions.get(f"pos_{self.portfolio_company_id}", {}).get("cost", 750000.0)
        financial_plan = self.scenario.get("financial_plan", {})
        liquidity_proceeds = financial_plan.get("liquidity_proceeds", 1200000.0)
        distribution_amount = financial_plan.get("distribution_amount", 1150000.0)
        position = self.state.portfolio_positions.get(f"pos_{self.portfolio_company_id}", {})
        current_value = float(position.get("current_value", investment_amount) or investment_amount)
        follow_on_reserve = self._follow_on_reserve_amount()
        bridge_amount = round(max(follow_on_reserve, investment_amount * 0.20), 2)
        down_round_value = round(current_value * 0.60, 2)
        partial_exit_proceeds = round(float(liquidity_proceeds) * 0.45, 2)
        partial_exit_remaining_nav = round(max(current_value - partial_exit_proceeds, 0), 2)
        regulatory_cost = round(investment_amount * 0.03, 2)
        distribution_event = next((event for event in reversed(self.events) if event.event_type == "Distribution"), None)
        waterfall = (distribution_event.payload.get("waterfall") if distribution_event else None) or self._waterfall(float(distribution_amount))
        management_fee = self.state.funds[self.fund_id].get("management_fees_paid", 0)
        reserve_required = self.state.funds[self.fund_id].get("reserve_required", self._reserve_requirement())
        projected_reserve = self.state.funds[self.fund_id].get("reserve_projected_after_distribution", 0)
        reserve_shortfall = self.state.funds[self.fund_id].get("reserve_shortfall", 0)
        first_call_amount = (
            float((self._capital_call_schedule()[0] or {}).get("amount", 0))
            if self._capital_call_schedule()
            else float(called)
        )
        default_remedy = self._default_remedy(first_call_amount)
        audit_exceptions_count = self.state.funds[self.fund_id].get("audit_exceptions_count", 0)
        branches = {
            "base": {
                "status": "simulated",
                "events": [
                    "FundClosing",
                    "CapitalCallIssued",
                    "LPPaymentReceived",
                    "ICApproval",
                    "InvestmentExecution",
                    "LiquidityEvent",
                    "Distribution",
                    "AuditReview",
                ],
                "financial_impact": {
                    "capital_called": called,
                    "capital_paid": called,
                    "investment_deployed": investment_amount,
                    "management_fee": management_fee,
                    "distribution_to_lp": waterfall["lp_distribution"],
                    "gp_carry": waterfall["gp_carry"],
                    "reserve_required": reserve_required,
                    "projected_reserve": projected_reserve,
                    "reserve_shortfall": reserve_shortfall,
                },
                "state_impact": {
                    "lp_default_status": "none",
                    "deal_status": "realized",
                    "ledger_balanced": self.state.ledger_summary.get("balanced", False),
                    "audit_exceptions": audit_exceptions_count,
                },
                "summary": f"{self.lp_name} pays on time, IC approves, {self.fund_name} invests in {self.portfolio_company_name}, liquidity and distribution occur.",
            },
            "lp_default": {
                "status": "simulated_alternative",
                "events": [
                    "CapitalCallIssued",
                    "CapitalCallDue",
                    "LPDefault",
                    "DefaultPenaltyAccrued",
                    "VotingRightsSuspended",
                ],
                "financial_impact": {
                    "capital_called": called,
                    "capital_paid": 0,
                    "default_penalty": default_remedy["default_penalty"],
                    "default_interest_annual_rate": default_remedy["default_interest_annual_rate"],
                    "investment_deployed": 0,
                    "management_fee": 0,
                },
                "state_impact": {
                    "lp_default_status": "defaulted",
                    "capital_call_obligation": "breached",
                    "cure_period_days": default_remedy["cure_period_days"],
                    "voting_rights": "suspended" if default_remedy["voting_rights_suspended"] else "unchanged",
                    "new_deployments": "blocked" if default_remedy["new_deployments_blocked"] else "allowed",
                },
                "summary": f"{self.lp_name} misses the capital call due date, triggering default remedies and blocking {self.fund_name}'s planned deployment.",
            },
            "ic_rejection": {
                "status": "simulated_alternative",
                "events": [
                    "DealEvaluation",
                    "ComplianceCheck",
                    "ICMeeting",
                    "ICRejected",
                    "DealTerminated",
                ],
                "financial_impact": {
                    "capital_called": called,
                    "capital_paid": called,
                    "investment_deployed": 0,
                    "cash_preserved": called,
                    "management_fee": management_fee,
                    "reserve_required": reserve_required,
                },
                "state_impact": {
                    "deal_status": "rejected",
                    "portfolio_position": "not_created",
                    "deployment_delay": True,
                    "follow_on_action": "source_new_deal_or_release_capital",
                },
                "summary": f"IC approval for {self.portfolio_company_name} falls below threshold, preserving cash but delaying {self.fund_name} deployment.",
            },
            "regulatory_delay": {
                "status": "simulated_alternative",
                "events": [
                    "DealEvaluation",
                    "ComplianceCheck",
                    "RegulatoryDelay",
                    "DelayedICMeeting",
                    "DelayedInvestmentExecution",
                ],
                "financial_impact": {
                    "capital_called": called,
                    "capital_paid": called,
                    "investment_deployed": investment_amount,
                    "delay_days": 45,
                    "management_fee": management_fee,
                    "reserve_required": reserve_required,
                },
                "state_impact": {
                    "deal_status": "delayed_then_executed",
                    "compliance_status": "cleared_after_delay",
                    "reporting_shifted": True,
                },
                "summary": f"Regulatory review delays the {self.portfolio_company_name} execution by 45 days, shifting deployment and reporting timing.",
            },
            "early_liquidity": {
                "status": "simulated_alternative",
                "events": [
                    "InvestmentExecution",
                    "LiquidityEvent",
                    "Distribution",
                    "AuditReview",
                ],
                "financial_impact": {
                    "investment_deployed": investment_amount,
                    "liquidity_proceeds": liquidity_proceeds,
                    "distribution_to_lp": waterfall["lp_distribution"],
                    "gp_carry": waterfall["gp_carry"],
                    "management_fee": management_fee,
                    "reserve_required": reserve_required,
                    "reserve_shortfall": reserve_shortfall,
                },
                "state_impact": {
                    "deal_status": "realized_early",
                    "lp_distribution_status": "paid",
                    "audit_exceptions": audit_exceptions_count,
                },
                "summary": f"{self.portfolio_company_name} realizes early, allowing the waterfall distribution to run within the 12-month window.",
            },
            "down_round": {
                "status": "simulated_alternative",
                "events": [
                    "QuarterlyNAVReview",
                    "DownRoundFinancing",
                    "ICValuationReview",
                    "LPUpdate",
                ],
                "financial_impact": {
                    "investment_deployed": investment_amount,
                    "pre_money_value": current_value,
                    "post_down_round_value": down_round_value,
                    "valuation_change_percent": -0.40,
                    "nav_impairment": round(current_value - down_round_value, 2),
                    "follow_on_reserve_needed": follow_on_reserve,
                },
                "state_impact": {
                    "deal_status": "active_down_round",
                    "valuation_status": "impaired",
                    "lp_reporting": "valuation_update_required",
                },
                "summary": f"{self.portfolio_company_name} raises a down round, reducing carrying value and requiring IC valuation support before LP reporting.",
            },
            "bridge_financing": {
                "status": "simulated_alternative",
                "events": [
                    "RunwayReview",
                    "BridgeFinancingRequest",
                    "ICBridgeApproval",
                    "FollowOnReserveUse",
                ],
                "financial_impact": {
                    "investment_deployed": investment_amount,
                    "bridge_amount": bridge_amount,
                    "runway_months_added": 6,
                    "conversion_discount": 0.20,
                    "follow_on_reserve_used": min(follow_on_reserve, bridge_amount),
                },
                "state_impact": {
                    "deal_status": "bridge_supported",
                    "follow_on_action": "approve_bridge_or_preserve_reserve",
                    "runway_status": "extended",
                },
                "summary": f"{self.fund_name} evaluates a bridge financing for {self.portfolio_company_name}, trading follow-on reserve capacity for runway extension.",
            },
            "write_off": {
                "status": "simulated_alternative",
                "events": [
                    "PortfolioImpairmentReview",
                    "ICWriteOffDecision",
                    "LPWriteOffNotice",
                    "AuditReview",
                ],
                "financial_impact": {
                    "investment_deployed": investment_amount,
                    "write_off_amount": investment_amount,
                    "nav_impairment": investment_amount,
                    "remaining_position_nav": 0,
                    "distribution_to_lp": 0,
                },
                "state_impact": {
                    "deal_status": "written_off",
                    "write_off_status": "full_write_off",
                    "lp_reporting": "material_loss_notice_required",
                    "audit_exceptions": audit_exceptions_count + 1,
                },
                "summary": f"{self.portfolio_company_name} is fully written off, requiring IC approval, LP notice, NAV impairment support, and audit review.",
            },
            "delayed_exit": {
                "status": "simulated_alternative",
                "events": [
                    "ExitReadinessReview",
                    "BuyerDelayNotice",
                    "QuarterlyNAVUpdate",
                    "DistributionDelayNotice",
                ],
                "financial_impact": {
                    "investment_deployed": investment_amount,
                    "expected_exit_proceeds": liquidity_proceeds,
                    "delay_months": 9,
                    "distribution_deferred": distribution_amount,
                    "nav_carry_value": current_value,
                },
                "state_impact": {
                    "deal_status": "exit_delayed",
                    "exit_status": "delayed",
                    "lp_distribution_status": "deferred",
                    "reporting_shifted": True,
                },
                "summary": f"Exit timing slips by 9 months, preserving NAV but delaying LP distributions and investor reporting cadence.",
            },
            "partial_exit": {
                "status": "simulated_alternative",
                "events": [
                    "PartialSale",
                    "WaterfallPreview",
                    "ResidualPositionReview",
                    "LPDistributionNotice",
                ],
                "financial_impact": {
                    "investment_deployed": investment_amount,
                    "partial_exit_proceeds": partial_exit_proceeds,
                    "remaining_position_nav": partial_exit_remaining_nav,
                    "distribution_to_lp": self._waterfall(partial_exit_proceeds)["lp_distribution"],
                    "gp_carry": self._waterfall(partial_exit_proceeds)["gp_carry"],
                },
                "state_impact": {
                    "deal_status": "partially_realized",
                    "exit_status": "partial",
                    "residual_position": "active",
                },
                "summary": f"A partial exit returns some liquidity while leaving a residual {self.portfolio_company_name} position for future NAV and exit review.",
            },
            "regulatory_block": {
                "status": "simulated_alternative",
                "events": [
                    "RegulatoryBlockNotice",
                    "ComplianceEscalation",
                    "InvestmentHold",
                    "LPRiskUpdate",
                ],
                "financial_impact": {
                    "capital_called": called,
                    "capital_paid": called,
                    "investment_deployed": 0,
                    "compliance_cost": regulatory_cost,
                    "delay_days": 120,
                    "cash_preserved": max(called - regulatory_cost, 0),
                },
                "state_impact": {
                    "deal_status": "blocked",
                    "regulatory_status": "blocked",
                    "new_deployments": "blocked",
                    "reporting_shifted": True,
                },
                "summary": f"Regulatory block prevents deployment into {self.portfolio_company_name}, preserving capital but forcing compliance escalation and LP risk update.",
            },
            "lp_default_cure_or_waiver": {
                "status": "simulated_alternative",
                "events": [
                    "LPDefault",
                    "CureNotice",
                    "LPACCureOrWaiverReview",
                    "CapitalCallCured",
                ],
                "financial_impact": {
                    "capital_called": first_call_amount,
                    "capital_paid": first_call_amount,
                    "default_penalty": default_remedy["default_penalty"],
                    "cure_payment": round(first_call_amount + default_remedy["default_penalty"], 2),
                    "investment_deployed": investment_amount,
                },
                "state_impact": {
                    "lp_default_status": "cured",
                    "cure_period_days": default_remedy["cure_period_days"],
                    "voting_rights": "restored_after_cure",
                    "new_deployments": "allowed_after_cure_or_waiver",
                    "lpac_waiver_available": True,
                },
                "summary": f"{self.lp_name} cures or receives an LPAC waiver after default notice, restoring deployment capacity while preserving an audit trail.",
            },
        }

        governance_inputs = {
            "base": (
                ["waterfall_rule", "reserve_account", "audit_review"],
                ["Record LP distribution and GP carry.", "Archive audit-ready ledger pack."],
            ),
            "lp_default": (
                ["capital_call_notice", "default_remedies"],
                ["Issue default notice.", "Suspend voting rights if LPA permits.", "Block new deployments until cure or waiver."],
            ),
            "ic_rejection": (
                ["voting_threshold"],
                ["Record IC rejection.", "Prepare LP update on undeployed capital.", "Source replacement deal or release capital."],
            ),
            "regulatory_delay": (
                ["compliance_check", "voting_threshold"],
                ["Shift IC calendar.", "Update quarterly reporting timeline.", "Escalate regulatory clearance owner."],
            ),
            "early_liquidity": (
                ["waterfall_rule", "reserve_account", "audit_review"],
                ["Run pre-distribution reserve review.", "Prepare distribution notice.", "Schedule post-distribution audit check."],
            ),
            "down_round": (
                ["valuation_policy", "follow_on_reserve", "lp_reporting"],
                ["Refresh NAV support.", "Prepare LP valuation update.", "Review follow-on reserve before participating."],
            ),
            "bridge_financing": (
                ["follow_on_reserve", "ic_approval", "related_party_review"],
                ["Run bridge financing memo.", "Approve reserve usage or preserve dry powder.", "Update LP on runway and conversion risk."],
            ),
            "write_off": (
                ["valuation_policy", "audit_review", "lp_reporting"],
                ["Obtain IC write-off approval.", "Prepare material loss notice.", "Bind audit evidence for NAV impairment."],
            ),
            "delayed_exit": (
                ["exit_timing", "quarterly_reporting", "distribution_policy"],
                ["Update exit timing assumptions.", "Prepare delayed distribution LP note.", "Refresh quarterly NAV support."],
            ),
            "partial_exit": (
                ["waterfall_rule", "residual_position_review", "lp_reporting"],
                ["Run partial waterfall preview.", "Approve residual position carrying value.", "Prepare partial distribution notice."],
            ),
            "regulatory_block": (
                ["compliance_check", "investment_hold", "lp_reporting"],
                ["Escalate regulatory clearance.", "Hold deployment until block is cleared.", "Prepare LP risk update."],
            ),
            "lp_default_cure_or_waiver": (
                ["capital_call_notice", "default_remedies", "lpac_waiver"],
                ["Record cure payment or LPAC waiver.", "Restore voting/deployment status if permitted.", "Archive default-remedy evidence."],
            ),
        }
        for branch_id, branch in branches.items():
            triggered_terms, actions = governance_inputs[branch_id]
            branch["governance"] = self._branch_governance_profile(
                branch_id,
                branch.get("financial_impact", {}),
                branch.get("state_impact", {}),
                triggered_terms,
                actions,
            )

        risk_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        branch_risk_summary = [
            {
                "branch_id": branch_id,
                "risk_level": branch["governance"]["risk_level"],
                "risk_score": branch["governance"]["risk_score"],
                "primary_action": branch["governance"]["governance_actions"][0],
                "audit_flags_count": len(branch["governance"]["audit_flags"]),
            }
            for branch_id, branch in sorted(
                branches.items(),
                key=lambda item: (
                    risk_rank[item[1]["governance"]["risk_level"]],
                    item[1]["governance"]["risk_score"],
                ),
                reverse=True,
            )
        ]

        return {
            "schema_version": "0.1",
            "simulation_id": self.state.simulation_id,
            "scenario_expansion": {
                "schema_version": "0.1",
                "milestone": "portfolio_scenario_expansion_alpha",
                "generation_policy": "branch_comparison_only_does_not_mutate_base_ledger",
                "branch_count": len(branches),
                "coverage": [
                    "down_round",
                    "bridge_financing",
                    "write_off",
                    "delayed_exit",
                    "partial_exit",
                    "regulatory_block",
                    "lp_default_cure_or_waiver",
                ],
            },
            "risk_summary": branch_risk_summary,
            "branches": branches,
        }

    def _branch_summaries(self, branch_results: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "branch_id": branch_id,
                "status": result.get("status"),
                "summary": result.get("summary"),
                "risk_level": (result.get("governance") or {}).get("risk_level", "unknown"),
                "risk_score": (result.get("governance") or {}).get("risk_score", 0),
                "primary_action": ((result.get("governance") or {}).get("governance_actions") or [""])[0],
            }
            for branch_id, result in branch_results.get("branches", {}).items()
        ]

    def _write_run_state(self, status: str) -> None:
        payload = {
            "simulation_id": self.config["simulation_id"],
            "engine_type": "business_governance",
            "runner_status": status,
            "current_round": self.state.current_event_index,
            "business_events_count": len(self.events),
            "ledger_entries_count": len(self.ledger_entries),
            "updated_at": datetime.now().isoformat(),
        }
        self.run_state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.run_state_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _object_name_map(self) -> dict[str, str]:
        names = {
            self.fund_id: self.fund_name,
            self.gp_id: self.gp_name,
            self.lp_id: self.lp_name,
            self.portfolio_company_id: self.portfolio_company_name,
            "ic": "Investment Committee",
            "regulator": "Regulator",
            "auditor": "Auditor",
        }
        for contract in self.fund_terms.get("contracts", []):
            if contract.get("id"):
                names[contract["id"]] = contract.get("type", contract["id"])
        return names

    def _event_plan_summary(self) -> dict[str, Any]:
        generation = self.scenario.get("event_generation", {})
        planned_events = self.scenario.get("planned_events") or self._planned_events()
        return {
            "source": generation.get("source", "engine_default"),
            "strategy": generation.get("strategy", "engine_default_fund_governance_plan"),
            "planned_events_count": len(planned_events),
            "planned_event_types": [event.get("event_type") for event in planned_events],
        }
