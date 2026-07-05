import json
import shutil
import zipfile
from pathlib import Path

from app import create_app
from app.config import Config
from app.models.project import ProjectManager
from app.services.business_simulation import BusinessSimulationEngine
from app.services.simulation_runner import RunnerStatus, SimulationRunner


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEMO_CONFIG = BACKEND_ROOT / "uploads" / "simulations" / "demo_business" / "business" / "business_simulation_config.json"
DEMO_BUSINESS_DIR = DEMO_CONFIG.parent


def test_business_engine_runs_demo_and_balances_ledger():
    result = BusinessSimulationEngine(DEMO_CONFIG).run()

    assert result.event_count == 18
    assert result.ledger_entry_count == 6
    assert result.decision_count == 1
    assert result.rule_execution_count == 6
    assert result.state.ledger_summary["balanced"] is True

    state = json.loads((DEMO_BUSINESS_DIR / "state_snapshot.json").read_text(encoding="utf-8"))
    assert state["funds"]["fund_i"]["called_capital"] == 1_150_000
    assert state["funds"]["fund_i"]["paid_in_capital"] == 1_150_000
    assert state["funds"]["fund_i"]["unfunded_commitments"] == 8_850_000
    assert state["funds"]["fund_i"]["cash"] == 400_000
    assert state["funds"]["fund_i"]["management_fees_paid"] == 50_000
    assert state["funds"]["fund_i"]["carry_allocated"] == 14_000
    assert state["funds"]["fund_i"]["reserve_required"] == 250_000
    assert state["funds"]["fund_i"]["reserve_shortfall"] == 0
    assert state["funds"]["fund_i"]["reserve_compliant"] is True
    assert state["funds"]["fund_i"]["audit_exceptions_count"] == 0
    assert state["lps"]["lp_a"]["distributions_received"] == 1_136_000
    assert state["lifecycle"]["fund_lifecycle_summary"]["capital_call_rounds"] == 2
    assert state["lifecycle"]["capital_call_schedule"][1]["type"] == "follow_on"
    assert state["lifecycle"]["capital_call_schedule"][1]["amount"] == 150_000
    assert state["lifecycle"]["fund_lifecycle_summary"]["commitment_summary"]["unfunded_commitment"] == 8_850_000
    assert state["lifecycle"]["fund_lifecycle_summary"]["follow_on_reserve"]["status"] == "funded"
    assert state["lifecycle"]["fund_lifecycle_summary"]["lp_readiness_summary"]["status"] == "ready_for_lp_discussion"
    assert len(state["lifecycle"]["nav_snapshots"]) >= 6

    evidence = json.loads((DEMO_BUSINESS_DIR / "evidence_bindings.json").read_text(encoding="utf-8"))
    assert evidence["binding_policy"] == "evidence_only_does_not_mutate_ledger"
    assert evidence["bindings_count"] >= 10
    evidence_targets = {item["target_path"] for item in evidence["bindings"]}
    assert "fund_lifecycle_summary.commitment_summary" in evidence_targets
    assert "fund_lifecycle_summary.follow_on_reserve" in evidence_targets
    assert any(item["target_type"] == "nav_snapshot" for item in evidence["bindings"])
    assert evidence["audit_trail"][1]["step"] == "deterministic_runtime"


def test_business_engine_writes_branch_results():
    BusinessSimulationEngine(DEMO_CONFIG).run()

    branch_results = json.loads((DEMO_BUSINESS_DIR / "branch_results.json").read_text(encoding="utf-8"))
    branches = branch_results["branches"]

    assert set(branches) == {
        "base",
        "lp_default",
        "ic_rejection",
        "regulatory_delay",
        "early_liquidity",
        "down_round",
        "bridge_financing",
        "write_off",
        "delayed_exit",
        "partial_exit",
        "regulatory_block",
        "lp_default_cure_or_waiver",
    }
    assert branch_results["scenario_expansion"]["milestone"] == "portfolio_scenario_expansion_alpha"
    assert branch_results["scenario_expansion"]["branch_count"] == 12
    assert branch_results["scenario_expansion"]["generation_policy"] == "branch_comparison_only_does_not_mutate_base_ledger"
    assert branches["lp_default"]["state_impact"]["lp_default_status"] == "defaulted"
    assert branches["ic_rejection"]["financial_impact"]["investment_deployed"] == 0
    assert branches["regulatory_delay"]["financial_impact"]["delay_days"] == 45
    assert branches["down_round"]["financial_impact"]["valuation_change_percent"] == -0.40
    assert branches["bridge_financing"]["financial_impact"]["bridge_amount"] > 0
    assert branches["write_off"]["state_impact"]["write_off_status"] == "full_write_off"
    assert branches["delayed_exit"]["financial_impact"]["delay_months"] == 9
    assert branches["partial_exit"]["state_impact"]["exit_status"] == "partial"
    assert branches["regulatory_block"]["state_impact"]["regulatory_status"] == "blocked"
    assert branches["lp_default_cure_or_waiver"]["state_impact"]["lp_default_status"] == "cured"
    assert branches["base"]["financial_impact"]["management_fee"] == 50_000
    assert branches["base"]["financial_impact"]["distribution_to_lp"] == 1_136_000
    assert branches["base"]["financial_impact"]["gp_carry"] == 14_000
    assert branches["base"]["financial_impact"]["reserve_required"] == 250_000
    assert branches["base"]["financial_impact"]["projected_reserve"] == 250_000
    assert branches["base"]["governance"]["risk_level"] == "low"
    assert branches["base"]["governance"]["triggered_terms"] == ["waterfall_rule", "reserve_account", "audit_review"]
    assert branches["lp_default"]["financial_impact"]["default_penalty"] == 9863.01
    assert branches["lp_default"]["state_impact"]["cure_period_days"] == 15
    assert branches["lp_default"]["state_impact"]["new_deployments"] == "blocked"
    assert branches["lp_default"]["governance"]["risk_level"] == "critical"
    assert "Issue default notice." in branches["lp_default"]["governance"]["governance_actions"]
    assert branch_results["risk_summary"][0]["branch_id"] == "lp_default"
    assert branch_results["risk_summary"][0]["risk_level"] == "critical"


def test_business_simulation_api_smoke():
    app = create_app()
    client = app.test_client()

    run_response = client.post("/api/business-simulation/run", json={"simulation_id": "demo_business"})
    assert run_response.status_code == 200
    assert run_response.json["success"] is True
    assert run_response.json["data"]["events"] == 18
    assert run_response.json["data"]["ledger_balanced"] is True

    branch_response = client.get("/api/business-simulation/demo_business/outputs/branch_results.json")
    assert branch_response.status_code == 200
    assert branch_response.json["success"] is True
    assert len(branch_response.json["data"]["branches"]) == 12
    assert branch_response.json["data"]["scenario_expansion"]["branch_count"] == 12

    report_response = client.post("/api/business-simulation/demo_business/report")
    assert report_response.status_code == 200
    assert report_response.json["success"] is True

    markdown_response = client.get("/api/business-simulation/demo_business/outputs/business_report.md")
    assert markdown_response.status_code == 200
    assert "# Fund I 12-Month Governance Simulation" in markdown_response.json["data"]["content"]


def test_business_simulation_single_access_code_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "BUSINESS_DEMO_ACCESS_CODE", "fixture-beta-code")
    monkeypatch.setattr(Config, "BUSINESS_DEMO_OWNER_CODE", "")
    monkeypatch.setattr(Config, "BUSINESS_DEMO_ACCESS_REGISTRY_PATH", str(tmp_path / "missing-registry.json"))

    app = create_app()
    client = app.test_client()

    denied = client.get("/api/business-simulation/demo")
    assert denied.status_code == 401
    assert denied.json["code"] == "business_demo_access_required"

    allowed = client.get("/api/business-simulation/demo", headers={"X-Business-Demo-Access": "fixture-beta-code"})
    assert allowed.status_code == 200
    assert allowed.json["success"] is True

    status = client.get("/api/business-simulation/access/status")
    assert status.status_code == 200
    assert status.json["data"]["access_required"] is True


def test_business_access_registry_owner_console_and_hash_gate(monkeypatch, tmp_path):
    registry_path = tmp_path / "business-demo-access-codes.json"
    monkeypatch.setattr(Config, "BUSINESS_DEMO_ACCESS_CODE", "")
    monkeypatch.setattr(Config, "BUSINESS_DEMO_OWNER_CODE", "fixture-owner-access")
    monkeypatch.setattr(Config, "BUSINESS_DEMO_ACCESS_REGISTRY_PATH", str(registry_path))

    app = create_app()
    client = app.test_client()

    no_owner = client.get("/api/business-simulation/access/admin/codes")
    assert no_owner.status_code == 401
    assert no_owner.json["code"] == "business_demo_owner_access_required"

    create_response = client.post(
        "/api/business-simulation/access/admin/codes",
        headers={"X-Business-Demo-Owner": "fixture-owner-access"},
        json={
            "label": "LP Alpha Group",
            "group": "LP_ALPHA",
            "code": "fixture-lp-alpha-code",
            "scopes": ["demo", "report", "meeting_pack"],
            "expires_at": "2099-12-31",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json["data"]["display_once_code"] == "fixture-lp-alpha-code"
    code_id = create_response.json["data"]["code_id"]

    registry_text = registry_path.read_text(encoding="utf-8")
    assert "fixture-lp-alpha-code" not in registry_text
    assert "pbkdf2_sha256" in registry_text

    denied = client.get("/api/business-simulation/demo")
    assert denied.status_code == 401
    assert denied.json["reason"] == "unknown_code"

    allowed = client.get("/api/business-simulation/demo", headers={"X-Business-Demo-Access": "fixture-lp-alpha-code"})
    assert allowed.status_code == 200
    assert allowed.json["success"] is True

    list_response = client.get(
        "/api/business-simulation/access/admin/codes",
        headers={"X-Business-Demo-Owner": "fixture-owner-access"},
    )
    assert list_response.status_code == 200
    assert list_response.json["data"]["codes"][0]["uses"] >= 1
    assert "code_hash" not in list_response.json["data"]["codes"][0]

    disable_response = client.patch(
        f"/api/business-simulation/access/admin/codes/{code_id}",
        headers={"X-Business-Demo-Owner": "fixture-owner-access"},
        json={"status": "disabled"},
    )
    assert disable_response.status_code == 200
    assert disable_response.json["data"]["status"] == "disabled"

    disabled = client.get("/api/business-simulation/demo", headers={"X-Business-Demo-Access": "fixture-lp-alpha-code"})
    assert disabled.status_code == 401
    assert disabled.json["reason"] == "disabled"


def test_business_simulation_create_api_can_replace_oasis_slot():
    app = create_app()
    client = app.test_client()
    simulation_id = "bus_test_api_slot"
    simulation_dir = BACKEND_ROOT / "uploads" / "simulations" / simulation_id
    project = ProjectManager.create_project(name="Business Slot Test")
    project.graph_id = "graph_test"
    project.engine_type = "business_governance"
    project.simulation_requirement = "模擬基金 LP 進入後的 capital call, IC decision, distribution, audit flow."
    project.analysis_summary = "A fund-governance project with LP, GP, IC, LPA, and portfolio company entities."
    project.ontology = {
        "entity_types": [
            {"name": "LimitedPartner", "examples": ["Anchor Family Office"]},
            {"name": "GeneralPartner", "examples": ["North Star GP"]},
            {"name": "InvestmentCommittee"},
            {"name": "PortfolioCompany", "examples": ["Culture Platform Co"]},
            {"name": "InvestmentFund", "examples": ["Culture Growth"]},
        ],
        "edge_types": [{"name": "commits_capital"}, {"name": "approves_investment"}],
    }
    ProjectManager.save_project(project)
    ProjectManager.save_extracted_text(
        project.project_id,
        "基金规模 30000000 USD。LP commitment 10000000 USD，投资收益目标 20%。Capital call 10%。"
        "Annual management fee 2.5%。IC approval threshold 75%。Preferred return 9%。"
        "GP carry 25%。Default interest 13%，cure period 20 days。"
        "Reserve account minimum USD 300000 and 6% of called capital。Audit materiality USD 150000。"
    )
    reloaded_project = ProjectManager.get_project(project.project_id)
    assert reloaded_project.engine_type == "business_governance"

    if simulation_dir.exists():
        shutil.rmtree(simulation_dir)

    try:
        create_response = client.post("/api/business-simulation/create", json={
            "simulation_id": simulation_id,
            "project_id": project.project_id,
        })
        assert create_response.status_code == 200
        assert create_response.json["success"] is True
        assert create_response.json["data"]["engine_type"] == "business_governance"
        assert create_response.json["data"]["source_project"]["project_id"] == project.project_id
        assert create_response.json["data"]["source_project"]["suggested_names"]["fund"] == "Culture Growth Governance Fund"
        assert create_response.json["data"]["source_project"]["financial_hints"]["commit_policy"] == "hints_only_not_committed_to_ledger"
        assert create_response.json["data"]["current_revision_id"] == "rev_0001"

        initial_revisions = json.loads((simulation_dir / "business" / "scenario_revisions.json").read_text(encoding="utf-8"))
        assert initial_revisions["current_revision_id"] == "rev_0001"
        assert initial_revisions["revisions"][0]["change_type"] == "initial_template"
        assert initial_revisions["revisions"][0]["file_digests"]["scenario_yaml"]

        state = json.loads((simulation_dir / "state.json").read_text(encoding="utf-8"))
        assert state["project_id"] == project.project_id
        assert state["graph_id"] == "graph_test"
        assert "capital call" in state["simulation_requirement"]
        initial_run_state = json.loads((simulation_dir / "run_state.json").read_text(encoding="utf-8"))
        assert initial_run_state["runner_status"] == "idle"

        fund_terms = (simulation_dir / "business" / "fund_terms.yaml").read_text(encoding="utf-8")
        assert "Culture Growth Governance Fund" in fund_terms
        assert "North Star GP" in fund_terms
        assert "Anchor Family Office" in fund_terms
        assert "Culture Platform Co" in fund_terms
        scenario_yaml = (simulation_dir / "business" / "scenario.yaml").read_text(encoding="utf-8")
        assert "planned_events:" in scenario_yaml
        assert "deterministic_fund_governance_plan_v1" in scenario_yaml
        assert "generated_from: project_seed" in scenario_yaml
        assert "financial_plan:" in scenario_yaml
        assert "capital_call_amount: 1000000.0" in scenario_yaml
        assert "investment_amount: 750000.0" in scenario_yaml
        assert "proposed_financial_plan:" in scenario_yaml
        assert "proposed_fund_terms:" in scenario_yaml
        assert "proposal_only_requires_user_confirmation" in scenario_yaml

        run_response = client.post("/api/business-simulation/run", json={"simulation_id": simulation_id})
        assert run_response.status_code == 200
        assert run_response.json["success"] is True
        assert run_response.json["data"]["events"] == 18
        assert run_response.json["data"]["ledger_balanced"] is True

        report_context = json.loads((simulation_dir / "business" / "report_context.json").read_text(encoding="utf-8"))
        assert report_context["source_project"]["project_id"] == project.project_id
        assert "LimitedPartner" in report_context["source_project"]["ontology_entity_types"]
        assert "2026" not in report_context["source_project"]["financial_hints"]["amounts"]
        assert "10000000 USD" in report_context["source_project"]["financial_hints"]["amounts"]
        assert report_context["title"] == "Culture Growth Governance Fund 12-Month Governance Simulation"
        assert any("Culture Platform Co" in item["summary"] for item in report_context["timeline"])
        assert report_context["object_name_map"]["fund_i"] == "Culture Growth Governance Fund"
        assert report_context["object_name_map"]["portco_a"] == "Culture Platform Co"
        assert report_context["event_plan_summary"]["source"] == "project_seed"
        assert report_context["event_plan_summary"]["planned_events_count"] == 14
        assert "ManagementFeePayment" in report_context["event_plan_summary"]["planned_event_types"]
        assert "ReserveAccountReview" in report_context["event_plan_summary"]["planned_event_types"]
        assert "InvestmentExecution" in report_context["event_plan_summary"]["planned_event_types"]
        assert "FollowOnReserveReview" in report_context["event_plan_summary"]["planned_event_types"]
        assert "FollowOnCapitalCall" in report_context["event_plan_summary"]["planned_event_types"]
        assert report_context["financial_plan"]["source"] == "fund_terms_and_project_seed"
        assert report_context["financial_plan"]["investment_amount"] == 750000.0
        assert report_context["financial_plan"]["follow_on_reserve_amount"] == 150000.0
        assert report_context["fund_terms_summary"]["management_fee"]["annual_rate"] == 0.02
        assert report_context["fund_terms_summary"]["default_remedies"]["cure_period_days"] == 15
        assert report_context["fund_terms_summary"]["reserve_account"]["minimum_cash"] == 250000
        assert report_context["fund_terms_summary"]["voting_threshold"]["threshold_percent"] == 66.67
        assert report_context["fund_terms_summary"]["waterfall_rule"]["preferred_return_rate"] == 0.08
        assert report_context["fund_terms_summary"]["audit_review"]["required_checks"] == [
            "ledger_balanced",
            "reserve_account_reviewed",
            "waterfall_rule_applied",
        ]
        assert report_context["source_project"]["fund_term_hints"]["commit_policy"] == "hints_only_not_committed_to_rules"
        assert "2.5%" in report_context["source_project"]["fund_term_hints"]["percentages"]
        assert report_context["proposed_fund_terms"]["status"] == "not_committed_to_rules"
        assert report_context["proposed_fund_terms"]["commit_policy"] == "proposal_only_requires_user_confirmation"
        assert report_context["proposed_fund_terms"]["proposals"]["management_fee"]["parameters"]["annual_rate"] == 0.025
        assert report_context["proposed_fund_terms"]["proposals"]["voting_threshold"]["parameters"]["threshold_percent"] == 75
        assert report_context["proposed_fund_terms"]["proposals"]["preferred_return"]["parameters"]["preferred_return_rate"] == 0.09
        assert report_context["proposed_fund_terms"]["proposals"]["gp_carry"]["parameters"]["gp_carry"] == 0.25
        assert report_context["proposed_fund_terms"]["proposals"]["default_remedies"]["parameters"]["cure_period_days"] == 20
        assert report_context["proposed_fund_terms"]["proposals"]["reserve_account"]["parameters"]["minimum_cash"] == 300000.0
        assert report_context["proposed_fund_terms"]["proposals"]["audit_review"]["parameters"]["materiality_threshold"] == 150000.0
        assert report_context["reserve_summary"]["required"] == 250000.0
        assert report_context["reserve_summary"]["shortfall"] == 0
        assert report_context["governance_summary"]["reserve_compliant"] is True
        assert report_context["governance_summary"]["audit_exceptions"] == 0
        assert report_context["governance_summary"]["waterfall_applied"] is True
        assert report_context["proposed_financial_plan"]["status"] == "not_committed_to_ledger"
        assert report_context["proposed_financial_plan"]["commit_policy"] == "proposal_only_requires_user_confirmation"
        assert report_context["proposed_financial_plan"]["proposals"]["lp_commitment"]["value"] == 30000000.0
        assert report_context["proposed_financial_plan"]["proposals"]["capital_call_amount"]["value"] == 3000000.0
        assert report_context["cashflow_summary"]["capital_called"] == 1150000.0
        assert report_context["cashflow_summary"]["capital_paid"] == 1150000.0
        assert report_context["cashflow_summary"]["unfunded_commitment"] == 8850000.0
        assert report_context["cashflow_summary"]["capital_call_rounds"] == 2
        assert report_context["fund_lifecycle_summary"]["focus"] == "lp_onboarding_capital_strategy"
        assert report_context["fund_lifecycle_summary"]["capital_call_rounds"] == 2
        assert report_context["fund_lifecycle_summary"]["commitment_summary"]["called_capital"] == 1150000.0
        assert report_context["fund_lifecycle_summary"]["commitment_summary"]["unfunded_commitment"] == 8850000.0
        assert report_context["fund_lifecycle_summary"]["follow_on_reserve"]["status"] == "funded"
        assert report_context["lp_readiness_summary"]["status"] == "ready_for_lp_discussion"
        assert report_context["capital_call_schedule"][1]["type"] == "follow_on"
        assert report_context["capital_call_schedule"][1]["amount"] == 150000.0
        assert len(report_context["nav_snapshots"]) >= 6
        assert report_context["evidence_bindings"]["binding_policy"] == "evidence_only_does_not_mutate_ledger"
        assert report_context["evidence_bindings"]["bindings_count"] >= 20
        binding_targets = {item["target_path"] for item in report_context["evidence_bindings"]["bindings"]}
        assert "proposed_financial_plan.proposals.lp_commitment" in binding_targets
        assert "proposed_fund_terms.proposals.management_fee" in binding_targets
        assert "fund_lifecycle_summary.commitment_summary" in binding_targets
        assert any(item["source_snippet"] for item in report_context["evidence_bindings"]["bindings"])
        assert "20%" in report_context["source_project"]["financial_hints"]["percentages"]
        assert "Culture Platform Co" in report_context["branch_results"]["branches"]["base"]["summary"]
        assert "Culture Growth Governance Fund" in report_context["branch_results"]["branches"]["ic_rejection"]["summary"]
        assert report_context["portfolio_scenario_expansion"]["milestone"] == "portfolio_scenario_expansion_alpha"
        assert report_context["portfolio_scenario_expansion"]["branch_count"] == 12
        assert "write_off" in report_context["portfolio_scenario_expansion"]["coverage"]
        assert "regulatory_block" in report_context["branch_results"]["branches"]

        term_commit_response = client.post(f"/api/business-simulation/{simulation_id}/fund-terms/commit")
        assert term_commit_response.status_code == 200
        assert term_commit_response.json["success"] is True
        assert term_commit_response.json["data"]["rerun_required"] is True
        assert term_commit_response.json["data"]["fund_terms"]["committed"]["management_fee"]["parameters"]["annual_rate"] == 0.025
        assert term_commit_response.json["data"]["revision"]["revision_id"] == "rev_0002"
        assert term_commit_response.json["data"]["revision"]["change_type"] == "fund_terms_commit"

        committed_terms_scenario_yaml = (simulation_dir / "business" / "scenario.yaml").read_text(encoding="utf-8")
        assert "status: committed_to_rules" in committed_terms_scenario_yaml
        committed_terms_yaml = (simulation_dir / "business" / "fund_terms.yaml").read_text(encoding="utf-8")
        assert "threshold_percent: 75.0" in committed_terms_yaml
        assert "minimum_cash: 300000.0" in committed_terms_yaml

        terms_run_response = client.post("/api/business-simulation/run", json={"simulation_id": simulation_id})
        assert terms_run_response.status_code == 200
        assert terms_run_response.json["success"] is True
        terms_report_context = json.loads((simulation_dir / "business" / "report_context.json").read_text(encoding="utf-8"))
        assert terms_report_context["fund_terms_summary"]["management_fee"]["annual_rate"] == 0.025
        assert terms_report_context["fund_terms_summary"]["voting_threshold"]["threshold_percent"] == 75
        assert terms_report_context["fund_terms_summary"]["waterfall_rule"]["preferred_return_rate"] == 0.09
        assert terms_report_context["fund_terms_summary"]["waterfall_rule"]["gp_carry"] == 0.25
        assert terms_report_context["fund_terms_summary"]["default_remedies"]["default_interest_annual_rate"] == 0.13
        assert terms_report_context["fund_terms_summary"]["default_remedies"]["cure_period_days"] == 20
        assert terms_report_context["fund_terms_summary"]["reserve_account"]["minimum_cash"] == 300000.0
        assert terms_report_context["fund_terms_summary"]["reserve_account"]["rate_of_called_capital"] == 0.06
        assert terms_report_context["fund_terms_summary"]["audit_review"]["materiality_threshold"] == 150000.0
        assert terms_report_context["proposed_fund_terms"]["status"] == "committed_to_rules"
        assert terms_report_context["reserve_summary"]["required"] == 300000.0
        assert terms_report_context["reserve_summary"]["shortfall"] == 62500.0
        assert terms_report_context["governance_summary"]["reserve_compliant"] is False
        assert terms_report_context["branch_risk_summary"][0]["branch_id"] == "lp_default"
        assert terms_report_context["branch_results"]["risk_summary"][0]["risk_level"] == "critical"
        assert terms_report_context["branch_results"]["branches"]["base"]["governance"]["risk_level"] == "medium"
        assert terms_report_context["branch_results"]["branches"]["base"]["governance"]["audit_flags"][0]["severity"] == "medium"
        assert "Reserve shortfall" in terms_report_context["branch_results"]["branches"]["base"]["governance"]["audit_flags"][0]["message"]
        assert terms_report_context["branch_results"]["branches"]["early_liquidity"]["governance"]["risk_level"] == "medium"

        commit_response = client.post(f"/api/business-simulation/{simulation_id}/financial-plan/commit")
        assert commit_response.status_code == 200
        assert commit_response.json["success"] is True
        assert commit_response.json["data"]["rerun_required"] is True
        assert commit_response.json["data"]["financial_plan"]["source"] == "committed_proposed_financial_plan"
        assert commit_response.json["data"]["financial_plan"]["capital_call_amount"] == 3000000.0
        assert commit_response.json["data"]["revision"]["revision_id"] == "rev_0003"
        assert commit_response.json["data"]["revision"]["parent_revision_id"] == "rev_0002"
        assert commit_response.json["data"]["revision"]["change_type"] == "financial_plan_commit"

        committed_scenario_yaml = (simulation_dir / "business" / "scenario.yaml").read_text(encoding="utf-8")
        assert "source: committed_proposed_financial_plan" in committed_scenario_yaml
        assert "amount: 3000000.0" in committed_scenario_yaml

        committed_run_response = client.post("/api/business-simulation/run", json={"simulation_id": simulation_id})
        assert committed_run_response.status_code == 200
        assert committed_run_response.json["success"] is True
        assert committed_run_response.json["data"]["ledger_balanced"] is True

        committed_report_context = json.loads((simulation_dir / "business" / "report_context.json").read_text(encoding="utf-8"))
        assert committed_report_context["financial_plan"]["source"] == "committed_proposed_financial_plan"
        assert committed_report_context["financial_plan"]["investment_amount"] == 2250000.0
        assert committed_report_context["proposed_financial_plan"]["status"] == "committed_to_financial_plan"
        assert committed_report_context["cashflow_summary"]["capital_called"] == 3450000.0
        assert committed_report_context["cashflow_summary"]["capital_paid"] == 3450000.0
        assert committed_report_context["cashflow_summary"]["unfunded_commitment"] == 26550000.0
        assert committed_report_context["cashflow_summary"]["capital_call_rounds"] == 2
        assert committed_report_context["cashflow_summary"]["fees"] == 187500.0
        assert committed_report_context["cashflow_summary"]["distributions"] == 3405000.0
        assert committed_report_context["financial_plan"]["follow_on_reserve_amount"] == 450000.0
        assert committed_report_context["capital_call_schedule"][1]["amount"] == 450000.0
        assert committed_report_context["fund_lifecycle_summary"]["commitment_summary"]["unfunded_commitment"] == 26550000.0
        assert committed_report_context["fund_lifecycle_summary"]["nav_summary"]["net_asset_value"] == 1162500.0
        assert committed_report_context["reserve_summary"]["required"] == 300000.0
        assert committed_report_context["reserve_summary"]["shortfall"] == 0
        assert committed_report_context["governance_summary"]["audit_exceptions"] == 0

        scenario_patch_payload = {
            "patch": {
                "financial_plan": {
                    "distribution_amount": 3405000.0,
                },
                "fund_terms": {
                    "management_fee": {
                        "annual_rate": 0.03,
                    },
                    "reserve_account": {
                        "minimum_cash": 800000.0,
                    },
                },
            }
        }
        patch_preview_response = client.post(
            f"/api/business-simulation/{simulation_id}/scenario-patch/preview",
            json=scenario_patch_payload,
        )
        assert patch_preview_response.status_code == 200
        assert patch_preview_response.json["success"] is True
        patch_preview = patch_preview_response.json["data"]
        assert patch_preview["rerun_required"] is True
        assert patch_preview["impact_preview"]["management_fee_amount"] == 225000.0
        assert patch_preview["impact_preview"]["reserve_required"] == 800000.0
        assert patch_preview["impact_preview"]["reserve_shortfall"] == 80000.0
        assert "fund_terms.management_fee.annual_rate" in {item["path"] for item in patch_preview["changed_paths"]}
        assert "fund_terms.reserve_account.minimum_cash" in {item["path"] for item in patch_preview["changed_paths"]}

        patch_commit_response = client.post(
            f"/api/business-simulation/{simulation_id}/scenario-patch/commit",
            json=scenario_patch_payload,
        )
        assert patch_commit_response.status_code == 200
        assert patch_commit_response.json["success"] is True
        assert patch_commit_response.json["data"]["status"] == "committed"
        assert patch_commit_response.json["data"]["rerun_required"] is True
        assert patch_commit_response.json["data"]["revision"]["revision_id"] == "rev_0004"
        assert patch_commit_response.json["data"]["revision"]["parent_revision_id"] == "rev_0003"
        assert patch_commit_response.json["data"]["revision"]["change_type"] == "manual_scenario_patch_commit"

        scenario_patch_output = json.loads((simulation_dir / "business" / "scenario_patch.json").read_text(encoding="utf-8"))
        assert scenario_patch_output["status"] == "committed"
        assert scenario_patch_output["commit_policy"] == "manual_patch_requires_explicit_commit_before_rerun"
        assert scenario_patch_output["revision"]["revision_id"] == "rev_0004"
        scenario_revisions = json.loads((simulation_dir / "business" / "scenario_revisions.json").read_text(encoding="utf-8"))
        assert scenario_revisions["current_revision_id"] == "rev_0004"
        assert [item["revision_id"] for item in scenario_revisions["revisions"]] == [
            "rev_0001",
            "rev_0002",
            "rev_0003",
            "rev_0004",
        ]
        patched_scenario_yaml = (simulation_dir / "business" / "scenario.yaml").read_text(encoding="utf-8")
        assert "manual_scenario_patch:" in patched_scenario_yaml
        assert "source: manual_scenario_patch" in patched_scenario_yaml
        patched_terms_yaml = (simulation_dir / "business" / "fund_terms.yaml").read_text(encoding="utf-8")
        assert "annual_rate: 0.03" in patched_terms_yaml
        assert "minimum_cash: 800000.0" in patched_terms_yaml

        patched_run_response = client.post("/api/business-simulation/run", json={"simulation_id": simulation_id})
        assert patched_run_response.status_code == 200
        assert patched_run_response.json["success"] is True
        assert patched_run_response.json["data"]["ledger_balanced"] is True
        patched_report_context = json.loads((simulation_dir / "business" / "report_context.json").read_text(encoding="utf-8"))
        assert patched_report_context["manual_scenario_patch"]["status"] == "committed"
        assert patched_report_context["scenario_revision"]["current_revision_id"] == "rev_0004"
        assert patched_report_context["scenario_revision"]["revisions_count"] == 4
        assert patched_report_context["scenario_revision"]["latest_revision"]["change_type"] == "manual_scenario_patch_commit"
        assert patched_report_context["fund_terms_summary"]["management_fee"]["annual_rate"] == 0.03
        assert patched_report_context["fund_terms_summary"]["reserve_account"]["minimum_cash"] == 800000.0
        assert patched_report_context["financial_plan"]["source"] == "manual_scenario_patch"
        assert patched_report_context["cashflow_summary"]["fees"] == 225000.0
        assert patched_report_context["reserve_summary"]["required"] == 800000.0
        assert patched_report_context["reserve_summary"]["shortfall"] == 80000.0
        assert patched_report_context["governance_summary"]["reserve_compliant"] is False

        history_response = client.get("/api/business-simulation/history?limit=50")
        assert history_response.status_code == 200
        assert history_response.json["success"] is True
        history_ids = {item["simulation_id"] for item in history_response.json["data"]}
        assert simulation_id in history_ids

        report_response = client.post(f"/api/business-simulation/{simulation_id}/report")
        assert report_response.status_code == 200
        markdown = (simulation_dir / "business" / "business_report.md").read_text(encoding="utf-8")
        assert "## Source Project" in markdown
        assert "## Event Plan" in markdown
        assert "## Branch Risk Summary" in markdown
        assert "## Portfolio Scenario Expansion" in markdown
        assert "branch_comparison_only_does_not_mutate_base_ledger" in markdown
        assert "## Fund Terms" in markdown
        assert "## Manual Scenario Patch" in markdown
        assert "## Scenario Revision" in markdown
        assert "## Proposed Fund Terms" in markdown
        assert "## Financial Plan" in markdown
        assert "## Reserve Summary" in markdown
        assert "## Audit Summary" in markdown
        assert "## Proposed Financial Plan" in markdown
        assert "## Evidence Bindings" in markdown
        assert "## Financial Hints" in markdown
        assert "## Fund Term Hints" in markdown
        assert "proposal_only_requires_user_confirmation" in markdown
        assert "hints_only_not_committed_to_ledger" in markdown
        assert "hints_only_not_committed_to_rules" in markdown
        assert "Culture Growth Governance Fund" in markdown

        packet_response = client.post(f"/api/business-simulation/{simulation_id}/governance-packet")
        assert packet_response.status_code == 200
        assert packet_response.json["success"] is True
        assert packet_response.json["data"]["decision_status"] == "action_required"
        assert packet_response.json["data"]["review_status"] == "pending_review"
        assert packet_response.json["data"]["highest_risk_branch"]["branch_id"] == "lp_default"

        packet = json.loads((simulation_dir / "business" / "governance_packet.json").read_text(encoding="utf-8"))
        assert packet["packet_type"] == "governance_decision_packet"
        assert packet["decision_status"] == "action_required"
        assert packet["scenario_revision"]["current_revision_id"] == "rev_0004"
        assert packet["scenario_revision"]["revisions_count"] == 4
        assert packet["highest_risk_branch"]["risk_level"] == "critical"
        assert packet["key_metrics"]["reserve_shortfall"] == 80000.0
        assert any(item["decision_id"] == "reserve_shortfall_resolution" for item in packet["required_decisions"])
        assert any(item["decision_id"] == "highest_risk_branch_response" for item in packet["required_decisions"])
        assert packet["branch_actions"][0]["branch_id"] == "base"
        assert "branch_results.json" in {item["file"] for item in packet["evidence_index"]}
        assert "scenario_patch.json" in {item["file"] for item in packet["evidence_index"]}
        assert "scenario_revisions.json" in {item["file"] for item in packet["evidence_index"]}
        assert "governance_remediation_plan.json" in {item["file"] for item in packet["evidence_index"]}
        assert "evidence_bindings.json" in {item["file"] for item in packet["evidence_index"]}
        assert packet["evidence_bindings"]["bindings_count"] >= 20
        assert packet["evidence_bindings"]["binding_policy"] == "evidence_only_does_not_mutate_ledger"
        assert any(item["target_type"] == "lp_capital_lifecycle" for item in packet["evidence_bindings"]["key_bindings"])

        meeting_pack_response = client.post(f"/api/business-simulation/{simulation_id}/meeting-pack")
        assert meeting_pack_response.status_code == 200
        assert meeting_pack_response.json["success"] is True
        assert meeting_pack_response.json["data"]["pack_type"] == "lpac_ic_meeting_pack"
        assert meeting_pack_response.json["data"]["generation_policy"] == "export_only_does_not_mutate_ledger_or_review_state"
        assert meeting_pack_response.json["data"]["agenda_count"] == 6
        assert meeting_pack_response.json["data"]["decision_count"] >= 2
        assert meeting_pack_response.json["data"]["evidence_count"] >= 10
        assert meeting_pack_response.json["data"]["lp_readiness_status"]
        assert meeting_pack_response.json["data"]["files"]["docx"]["bytes"] > 1000
        assert meeting_pack_response.json["data"]["files"]["pdf"]["bytes"] > 1000

        meeting_pack = json.loads((simulation_dir / "business" / "meeting_pack.json").read_text(encoding="utf-8"))
        assert meeting_pack["lp_capital_brief"]["capital_call_rounds"] == 2
        assert meeting_pack["lp_capital_brief"]["unfunded_commitment"] >= 0
        assert meeting_pack["scenario_expansion"]["branch_count"] == 12
        assert "down_round" in meeting_pack["scenario_expansion"]["coverage"]
        assert meeting_pack["strategy_readiness"]["proposed_financial_commit_policy"] == "proposal_only_requires_user_confirmation"
        assert any(item["decision_id"] == "reserve_shortfall_resolution" for item in meeting_pack["decision_table"])
        assert any(item["target_type"] == "lp_capital_lifecycle" for item in meeting_pack["evidence_appendix"])

        meeting_markdown = (simulation_dir / "business" / "meeting_pack.md").read_text(encoding="utf-8")
        assert "## Meeting Agenda" in meeting_markdown
        assert "## LP Capital Brief" in meeting_markdown
        assert "## Portfolio Scenario Expansion" in meeting_markdown
        assert "## Decision Table" in meeting_markdown
        assert "## Risk Appendix" in meeting_markdown
        assert "## Evidence Appendix" in meeting_markdown
        with zipfile.ZipFile(simulation_dir / "business" / "meeting_pack.docx") as docx:
            assert "word/document.xml" in docx.namelist()
        assert (simulation_dir / "business" / "meeting_pack.pdf").read_bytes().startswith(b"%PDF-1.4")

        remediation_response = client.post(f"/api/business-simulation/{simulation_id}/governance-remediation-plan")
        assert remediation_response.status_code == 200
        assert remediation_response.json["success"] is True
        remediation_plan = remediation_response.json["data"]["preview"]
        assert remediation_plan["status"] == "ready_for_review"
        assert remediation_plan["adoption_allowed"] is True
        assert remediation_plan["scenario_revision"]["packet_revision_id"] == "rev_0004"
        assert remediation_plan["reserve_shortfall"] == 80000.0
        assert remediation_plan["recommended_option_id"] == "reduce_distribution_to_restore_reserve"
        options = {item["option_id"]: item for item in remediation_plan["options"]}
        assert options["reduce_distribution_to_restore_reserve"]["patch"]["financial_plan"]["distribution_amount"] == 3325000.0
        assert options["capital_call_top_up_for_reserve"]["patch"]["financial_plan"]["capital_call_amount"] == 3080000.0
        assert options["lpac_reserve_waiver"]["review_action"] == "waive_reserve"

        memo = (simulation_dir / "business" / "governance_memo.md").read_text(encoding="utf-8")
        assert "## Required Decisions" in memo
        assert "highest_risk_branch_response" in memo

        review = json.loads((simulation_dir / "business" / "governance_review.json").read_text(encoding="utf-8"))
        assert review["review_status"] == "pending_review"
        assert review["packet_digest"]
        assert review["scenario_revision_id"] == "rev_0004"
        assert review["requires_rerun"] is False

        review_response = client.get(f"/api/business-simulation/{simulation_id}/governance-review")
        assert review_response.status_code == 200
        assert review_response.json["success"] is True
        assert review_response.json["data"]["review_status"] == "pending_review"
        assert review_response.json["data"]["effective_review_status"] == "pending_review"
        assert review_response.json["data"]["packet_is_stale"] is False

        waive_response = client.post(f"/api/business-simulation/{simulation_id}/governance-review", json={
            "action": "waive_reserve",
            "actor": "LPAC Chair",
            "role": "LPAC",
            "note": "Approve waiver for test fixture.",
        })
        assert waive_response.status_code == 200
        assert waive_response.json["success"] is True
        assert waive_response.json["data"]["review"]["review_status"] == "approved_with_reserve_waiver"
        assert waive_response.json["data"]["review"]["approved_actions"][0]["type"] == "reserve_waiver"
        assert waive_response.json["data"]["review"]["requires_rerun"] is False

        rerun_review_response = client.post(f"/api/business-simulation/{simulation_id}/governance-review", json={
            "action": "request_rerun",
            "actor": "GP Reviewer",
            "role": "GP",
            "note": "Revise reserve policy and rerun.",
        })
        assert rerun_review_response.status_code == 200
        assert rerun_review_response.json["success"] is True
        assert rerun_review_response.json["data"]["review"]["review_status"] == "rerun_requested"
        assert rerun_review_response.json["data"]["review"]["requires_rerun"] is True

        stale_patch_response = client.post(
            f"/api/business-simulation/{simulation_id}/scenario-patch/commit",
            json={
                "patch": {
                    "fund_terms": {
                        "reserve_account": {"minimum_cash": 810000.0},
                    },
                }
            },
        )
        assert stale_patch_response.status_code == 200
        assert stale_patch_response.json["success"] is True
        assert stale_patch_response.json["data"]["revision"]["revision_id"] == "rev_0005"

        stale_review_response = client.get(f"/api/business-simulation/{simulation_id}/governance-review")
        assert stale_review_response.status_code == 200
        assert stale_review_response.json["success"] is True
        assert stale_review_response.json["data"]["packet_is_stale"] is True
        assert stale_review_response.json["data"]["packet_revision_id"] == "rev_0004"
        assert stale_review_response.json["data"]["current_revision_id"] == "rev_0005"
        assert stale_review_response.json["data"]["effective_review_status"] == "stale_packet_requires_regeneration"

        stale_plan_response = client.post(f"/api/business-simulation/{simulation_id}/governance-remediation-plan")
        assert stale_plan_response.status_code == 200
        assert stale_plan_response.json["success"] is True
        stale_plan = stale_plan_response.json["data"]["preview"]
        assert stale_plan["status"] == "blocked_stale_packet"
        assert stale_plan["adoption_allowed"] is False
        assert stale_plan["scenario_revision"]["packet_revision_id"] == "rev_0004"
        assert stale_plan["scenario_revision"]["current_revision_id"] == "rev_0005"

        stale_approve_response = client.post(f"/api/business-simulation/{simulation_id}/governance-review", json={
            "action": "approve",
            "actor": "LPAC Chair",
            "role": "LPAC",
            "note": "This should be blocked because packet is stale.",
        })
        assert stale_approve_response.status_code == 409
        assert stale_approve_response.json["success"] is False
        assert stale_approve_response.json["data"]["packet_revision_id"] == "rev_0004"
        assert stale_approve_response.json["data"]["current_revision_id"] == "rev_0005"

        stale_run_response = client.post("/api/business-simulation/run", json={"simulation_id": simulation_id})
        assert stale_run_response.status_code == 200
        stale_report_response = client.post(f"/api/business-simulation/{simulation_id}/report")
        assert stale_report_response.status_code == 200
        regenerated_packet_response = client.post(f"/api/business-simulation/{simulation_id}/governance-packet")
        assert regenerated_packet_response.status_code == 200
        assert regenerated_packet_response.json["success"] is True
        assert regenerated_packet_response.json["data"]["scenario_revision_id"] == "rev_0005"
        assert regenerated_packet_response.json["data"]["packet_is_stale"] is False
        regenerated_plan_response = client.post(f"/api/business-simulation/{simulation_id}/governance-remediation-plan")
        assert regenerated_plan_response.status_code == 200
        assert regenerated_plan_response.json["success"] is True
        assert regenerated_plan_response.json["data"]["preview"]["status"] == "ready_for_review"
        assert regenerated_plan_response.json["data"]["preview"]["scenario_revision"]["packet_revision_id"] == "rev_0005"
        recommended_option_id = regenerated_plan_response.json["data"]["preview"]["recommended_option_id"]
        adoption_preview_response = client.post(
            f"/api/business-simulation/{simulation_id}/governance-remediation-plan/options/{recommended_option_id}/preview"
        )
        assert adoption_preview_response.status_code == 200
        assert adoption_preview_response.json["success"] is True
        assert adoption_preview_response.json["data"]["source"]["type"] == "governance_remediation_option"
        assert adoption_preview_response.json["data"]["source"]["option_id"] == "reduce_distribution_to_restore_reserve"
        assert adoption_preview_response.json["data"]["impact_preview"]["reserve_shortfall"] == 0
        assert adoption_preview_response.json["data"]["patch"]["financial_plan"]["distribution_amount"] == 3315000.0

        adoption_commit_response = client.post(
            f"/api/business-simulation/{simulation_id}/governance-remediation-plan/options/{recommended_option_id}/commit"
        )
        assert adoption_commit_response.status_code == 200
        assert adoption_commit_response.json["success"] is True
        assert adoption_commit_response.json["data"]["source"]["type"] == "governance_remediation_option"
        assert adoption_commit_response.json["data"]["revision"]["revision_id"] == "rev_0006"
        assert adoption_commit_response.json["data"]["revision"]["change_type"] == "remediation_option_commit"
        assert adoption_commit_response.json["data"]["revision"]["source"]["remediation_option_id"] == "reduce_distribution_to_restore_reserve"

        adopted_run_response = client.post("/api/business-simulation/run", json={"simulation_id": simulation_id})
        assert adopted_run_response.status_code == 200
        assert adopted_run_response.json["success"] is True
        adopted_report_context = json.loads((simulation_dir / "business" / "report_context.json").read_text(encoding="utf-8"))
        assert adopted_report_context["scenario_revision"]["current_revision_id"] == "rev_0006"
        assert adopted_report_context["scenario_revision"]["latest_revision"]["change_type"] == "remediation_option_commit"
        assert adopted_report_context["reserve_summary"]["shortfall"] == 0
        assert adopted_report_context["governance_summary"]["reserve_compliant"] is True

        adopted_report_response = client.post(f"/api/business-simulation/{simulation_id}/report")
        assert adopted_report_response.status_code == 200
        adopted_packet_response = client.post(f"/api/business-simulation/{simulation_id}/governance-packet")
        assert adopted_packet_response.status_code == 200
        assert adopted_packet_response.json["success"] is True
        assert adopted_packet_response.json["data"]["scenario_revision_id"] == "rev_0006"
        adopted_plan_response = client.post(f"/api/business-simulation/{simulation_id}/governance-remediation-plan")
        assert adopted_plan_response.status_code == 200
        assert adopted_plan_response.json["success"] is True
        assert adopted_plan_response.json["data"]["preview"]["reserve_shortfall"] == 0

        packet_output = client.get(f"/api/business-simulation/{simulation_id}/outputs/governance_packet.json")
        assert packet_output.status_code == 200
        assert packet_output.json["success"] is True
        memo_output = client.get(f"/api/business-simulation/{simulation_id}/outputs/governance_memo.md")
        assert memo_output.status_code == 200
        assert "## Decision Packet" in memo_output.json["data"]["content"]
        review_output = client.get(f"/api/business-simulation/{simulation_id}/outputs/governance_review.json")
        assert review_output.status_code == 200
        assert review_output.json["success"] is True
        assert review_output.json["data"]["review_status"] == "pending_review"
        assert review_output.json["data"]["scenario_revision_id"] == "rev_0006"
        remediation_output = client.get(f"/api/business-simulation/{simulation_id}/outputs/governance_remediation_plan.json")
        assert remediation_output.status_code == 200
        assert remediation_output.json["success"] is True
        assert remediation_output.json["data"]["reserve_shortfall"] == 0
        assert remediation_output.json["data"]["recommended_option_id"] == "highest_risk_branch_action_plan"
        meeting_pack_output = client.get(f"/api/business-simulation/{simulation_id}/outputs/meeting_pack.json")
        assert meeting_pack_output.status_code == 200
        assert meeting_pack_output.json["success"] is True
        assert meeting_pack_output.json["data"]["pack_type"] == "lpac_ic_meeting_pack"
        meeting_markdown_output = client.get(f"/api/business-simulation/{simulation_id}/outputs/meeting_pack.md")
        assert meeting_markdown_output.status_code == 200
        assert "## Meeting Agenda" in meeting_markdown_output.json["data"]["content"]
        patch_output = client.get(f"/api/business-simulation/{simulation_id}/outputs/scenario_patch.json")
        assert patch_output.status_code == 200
        assert patch_output.json["success"] is True
        assert patch_output.json["data"]["source"]["type"] == "governance_remediation_option"
        assert patch_output.json["data"]["source"]["option_id"] == "reduce_distribution_to_restore_reserve"
        assert patch_output.json["data"]["revision"]["revision_id"] == "rev_0006"
        assert patch_output.json["data"]["impact_preview"]["reserve_shortfall"] == 0
        revisions_response = client.get(f"/api/business-simulation/{simulation_id}/scenario-revisions")
        assert revisions_response.status_code == 200
        assert revisions_response.json["success"] is True
        assert revisions_response.json["data"]["current_revision_id"] == "rev_0006"
        revisions_output = client.get(f"/api/business-simulation/{simulation_id}/outputs/scenario_revisions.json")
        assert revisions_output.status_code == 200
        assert revisions_output.json["success"] is True
        assert len(revisions_output.json["data"]["revisions"]) == 6
    finally:
        if simulation_dir.exists():
            shutil.rmtree(simulation_dir)
        ProjectManager.delete_project(project.project_id)


def test_legacy_ready_run_state_loads_as_idle():
    simulation_id = "legacy_ready_business_state"
    simulation_dir = BACKEND_ROOT / "uploads" / "simulations" / simulation_id
    shutil.rmtree(simulation_dir, ignore_errors=True)
    simulation_dir.mkdir(parents=True)
    try:
        (simulation_dir / "run_state.json").write_text(json.dumps({
            "simulation_id": simulation_id,
            "runner_status": "ready",
            "current_round": 0,
        }), encoding="utf-8")
        SimulationRunner._run_states.pop(simulation_id, None)

        state = SimulationRunner.get_run_state(simulation_id)

        assert state is not None
        assert state.runner_status == RunnerStatus.IDLE
    finally:
        SimulationRunner._run_states.pop(simulation_id, None)
        shutil.rmtree(simulation_dir, ignore_errors=True)
