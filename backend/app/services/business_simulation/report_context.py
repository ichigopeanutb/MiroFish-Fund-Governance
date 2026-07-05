"""Assemble report-ready context from a business simulation run."""

from __future__ import annotations

from .models import BusinessEvent, LedgerEntry, RuntimeState


def assemble_report_context(
    state: RuntimeState,
    events: list[BusinessEvent],
    ledger_entries: list[LedgerEntry],
    branch_summaries: list[dict],
    branch_results: dict | None = None,
) -> dict:
    fund = next(iter(state.funds.values()))
    lp = next(iter(state.lps.values()))
    total_called = fund.get("called_capital", 0)
    total_paid = fund.get("paid_in_capital", 0)
    total_distributions = lp.get("distributions_received", 0)
    lifecycle = state.lifecycle or {}
    fund_lifecycle_summary = lifecycle.get("fund_lifecycle_summary", {})
    nav_summary = fund_lifecycle_summary.get("nav_summary", {})
    commitment_summary = fund_lifecycle_summary.get("commitment_summary", {})
    fees = sum(
        line.debit
        for entry in ledger_entries
        for line in entry.lines
        if line.account == "management_fee_expense"
    )

    timeline = [
        {
            "simulation_time": event.simulation_time,
            "event_type": event.event_type,
            "summary": event.payload.get("summary", event.event_type),
            "object_refs": [obj.object_id for obj in event.touched_objects],
            "evidence_refs": [f"event_log.jsonl#{event.event_id}"],
        }
        for event in events
    ]
    audit_events = [event for event in events if event.event_type == "AuditReview"]
    audit_exceptions = [
        exception
        for event in audit_events
        for exception in event.payload.get("audit_exceptions", [])
    ]
    reserve_summary = {
        "required": fund.get("reserve_required", 0),
        "projected_after_distribution": fund.get("reserve_projected_after_distribution", 0),
        "shortfall": fund.get("reserve_shortfall", 0),
        "compliant": fund.get("reserve_compliant"),
    }
    waterfall_applied = any(
        "waterfall" in event.payload
        for event in events
        if event.event_type == "Distribution"
    )
    branch_risk_summary = (branch_results or {}).get("risk_summary", [])
    portfolio_scenario_expansion = (branch_results or {}).get("scenario_expansion", {})

    return {
        "schema_version": "0.1",
        "simulation_id": state.simulation_id,
        "engine_type": "business_governance",
        "title": f"{fund.get('name', 'Fund')} 12-Month Governance Simulation",
        "scenario_summary": {
            "scenario_id": state.scenario_id,
            "branch_id": state.branch_id,
            "branches": [branch["branch_id"] for branch in branch_summaries],
        },
        "executive_findings": [
            f"Base branch called {total_called:,.2f} and received {total_paid:,.2f}.",
            f"Final LP default status is {lp.get('default_status', 'none')}.",
            f"Ledger balanced: {state.ledger_summary.get('balanced', False)}.",
        ],
        "timeline": timeline,
        "cashflow_summary": {
            "capital_called": total_called,
            "capital_paid": total_paid,
            "unfunded_commitment": commitment_summary.get("unfunded_commitment", fund.get("unfunded_commitments", 0)),
            "capital_call_rounds": fund_lifecycle_summary.get("capital_call_rounds", 0),
            "distributions": total_distributions,
            "fees": fees,
            "penalties": lp.get("penalties_accrued", 0),
            "net_asset_value": nav_summary.get("net_asset_value", 0),
            "paid_in_multiple": nav_summary.get("paid_in_multiple", 0),
        },
        "governance_summary": {
            "decisions": len(state.decisions),
            "approvals": len([d for d in state.decisions.values() if d.get("result") == "approved"]),
            "rejections": len([d for d in state.decisions.values() if d.get("result") == "rejected"]),
            "vetoes": 0,
            "reserve_compliant": reserve_summary["compliant"],
            "audit_exceptions": len(audit_exceptions),
            "waterfall_applied": waterfall_applied,
        },
        "reserve_summary": reserve_summary,
        "fund_lifecycle_summary": fund_lifecycle_summary,
        "capital_call_schedule": lifecycle.get("capital_call_schedule", []),
        "nav_snapshots": lifecycle.get("nav_snapshots", []),
        "lp_readiness_summary": fund_lifecycle_summary.get("lp_readiness_summary", {}),
        "audit_summary": {
            "exceptions_count": len(audit_exceptions),
            "exceptions": audit_exceptions,
            "last_review": audit_events[-1].payload if audit_events else {},
        },
        "branch_risk_summary": branch_risk_summary,
        "branch_summaries": branch_summaries,
        "branch_results": branch_results or {},
        "portfolio_scenario_expansion": portfolio_scenario_expansion,
        "exceptions": audit_exceptions,
        "report_agent_hints": {
            "recommended_sections": [
                "Scenario and Object Map",
                "Capital Calls and Cashflow",
                "Governance Decisions",
                "Branch Risk Comparison",
                "Audit Trail",
            ]
        },
    }
