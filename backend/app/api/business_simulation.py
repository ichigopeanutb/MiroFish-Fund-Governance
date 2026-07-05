"""Business-governance simulation API routes.

These routes expose the new fund-operation simulator as a MiroFish simulation
backend without touching the existing OASIS-oriented /api/simulation routes.
"""

from __future__ import annotations

import json
import re
import traceback
import hashlib
import html
import hmac
import textwrap
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import jsonify, request
import yaml

from . import business_simulation_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.business_demo_access import BusinessDemoAccessRegistry
from ..services.business_simulation import BusinessSimulationEngine
from ..services.business_simulation.loader import load_structured_file, write_json
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.business_simulation")

SIMULATION_ROOT = Path(Config.OASIS_SIMULATION_DATA_DIR).resolve()
DEMO_BUSINESS_DIR = SIMULATION_ROOT / "demo_business" / "business"
ALLOWED_OUTPUT_FILES = {
    "compiled_world.json",
    "event_log.jsonl",
    "ledger.jsonl",
    "decision_records.jsonl",
    "rule_execution_records.jsonl",
    "branch_results.json",
    "state_snapshot.json",
    "report_context.json",
    "business_report.md",
    "governance_packet.json",
    "governance_memo.md",
    "governance_review.json",
    "governance_remediation_plan.json",
    "meeting_pack.json",
    "meeting_pack.md",
    "scenario_patch.json",
    "scenario_revisions.json",
    "evidence_bindings.json",
}

EDITABLE_FINANCIAL_FIELDS = {
    "lp_commitment",
    "capital_call_amount",
    "investment_amount",
    "liquidity_proceeds",
    "distribution_amount",
    "follow_on_reserve_amount",
}

EDITABLE_FUND_TERM_FIELDS = {
    "management_fee": {"annual_rate", "basis", "period_months"},
    "voting_threshold": {"matter", "threshold_percent"},
    "waterfall_rule": {"return_of_capital", "preferred_return_rate", "preferred_return_months", "gp_carry", "lp_profit_split"},
    "default_remedies": {"default_interest_annual_rate", "default_interest_days", "cure_period_days", "suspend_voting_rights", "block_new_deployments"},
    "reserve_account": {"minimum_cash", "rate_of_called_capital", "review_before_distribution"},
    "audit_review": {"materiality_threshold", "required_checks"},
}


def _access_registry() -> BusinessDemoAccessRegistry:
    return BusinessDemoAccessRegistry(Config.BUSINESS_DEMO_ACCESS_REGISTRY_PATH)


def _request_meta() -> dict:
    return {
        "remote_addr": request.remote_addr or "",
        "user_agent": request.headers.get("User-Agent", "")[:180],
    }


def _provided_business_access_code() -> str:
    provided_code = (request.headers.get("X-Business-Demo-Access") or "").strip()
    authorization = (request.headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        provided_code = authorization[7:].strip()
    return provided_code


def _provided_owner_code() -> str:
    provided_code = (request.headers.get("X-Business-Demo-Owner") or "").strip()
    authorization = (request.headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("owner "):
        provided_code = authorization[6:].strip()
    return provided_code


def _business_access_required() -> bool:
    return bool((Config.BUSINESS_DEMO_ACCESS_CODE or "").strip()) or _access_registry().has_codes()


def _required_access_scope() -> str:
    path = request.path or ""
    if "/meeting-pack" in path:
        return "meeting_pack"
    if any(marker in path for marker in [
        "/report",
        "/governance-packet",
        "/governance-review",
        "/governance-remediation-plan",
        "/outputs/",
    ]):
        return "report"
    return "demo"


def _access_status_payload() -> dict:
    registry = _access_registry()
    return {
        "edition": "MiroFish Fund Governance Edition",
        "access_required": _business_access_required(),
        "legacy_single_code_enabled": bool((Config.BUSINESS_DEMO_ACCESS_CODE or "").strip()),
        "owner_console_enabled": bool((Config.BUSINESS_DEMO_OWNER_CODE or "").strip()),
        "registry": registry.public_summary(),
        "registry_enabled": registry.has_codes(),
        "warning": "Private beta gate only. Do not commit real access codes or sensitive LP/fund data.",
    }


@business_simulation_bp.before_request
def _require_business_demo_access_code():
    path = request.path or ""
    if request.method == "OPTIONS":
        return None
    if path.endswith("/access/status") or path.endswith("/access/verify"):
        return None
    if "/access/admin/" in path:
        owner_code = (Config.BUSINESS_DEMO_OWNER_CODE or "").strip()
        if not owner_code:
            return jsonify({
                "success": False,
                "error": "Owner access console is disabled. Set BUSINESS_DEMO_OWNER_CODE outside git to enable it.",
                "code": "business_demo_owner_console_disabled",
            }), 403
        if hmac.compare_digest(_provided_owner_code(), owner_code):
            return None
        return jsonify({
            "success": False,
            "error": "Owner access code is required.",
            "code": "business_demo_owner_access_required",
        }), 401

    registry = _access_registry()
    required_scope = _required_access_scope()
    provided_code = _provided_business_access_code()
    if registry.has_codes():
        result = registry.verify(provided_code, required_scope=required_scope, request_meta=_request_meta())
        if result["allowed"]:
            return None
        return jsonify({
            "success": False,
            "error": "Business governance demo access code is required.",
            "code": "business_demo_access_required",
            "reason": result.get("reason"),
            "required_scope": required_scope,
        }), 401

    required_code = (Config.BUSINESS_DEMO_ACCESS_CODE or "").strip()
    if not required_code:
        return None
    if hmac.compare_digest(provided_code, required_code):
        return None
    return jsonify({
        "success": False,
        "error": "Business governance demo access code is required.",
        "code": "business_demo_access_required",
    }), 401


@business_simulation_bp.route("/access/status", methods=["GET"])
def get_business_demo_access_status():
    return jsonify({"success": True, "data": _access_status_payload()})


@business_simulation_bp.route("/access/verify", methods=["POST"])
def verify_business_demo_access_code():
    data = request.get_json(silent=True) or {}
    required_scope = data.get("required_scope") or "demo"
    provided_code = (data.get("code") or _provided_business_access_code()).strip()
    registry = _access_registry()
    if registry.has_codes():
        result = registry.verify(provided_code, required_scope=required_scope, request_meta=_request_meta())
        if result["allowed"]:
            return jsonify({
                "success": True,
                "data": {
                    "allowed": True,
                    "code": result["code"],
                    "access_status": _access_status_payload(),
                },
            })
        return jsonify({
            "success": False,
            "error": "Access code does not match an active beta group.",
            "code": "business_demo_access_required",
            "reason": result.get("reason"),
        }), 401

    required_code = (Config.BUSINESS_DEMO_ACCESS_CODE or "").strip()
    if not required_code:
        return jsonify({"success": True, "data": {"allowed": True, "access_status": _access_status_payload()}})
    if hmac.compare_digest(provided_code, required_code):
        return jsonify({
            "success": True,
            "data": {
                "allowed": True,
                "code": {
                    "label": "Legacy single beta code",
                    "group": "legacy",
                    "scopes": ["all"],
                },
                "access_status": _access_status_payload(),
            },
        })
    return jsonify({
        "success": False,
        "error": "Access code does not match. Please ask the project owner for the current beta code.",
        "code": "business_demo_access_required",
    }), 401


@business_simulation_bp.route("/access/admin/codes", methods=["GET"])
def list_business_demo_access_codes():
    return jsonify({
        "success": True,
        "data": {
            "codes": _access_registry().list_codes(),
            "access_status": _access_status_payload(),
        },
    })


@business_simulation_bp.route("/access/admin/codes", methods=["POST"])
def create_business_demo_access_code():
    data = request.get_json(silent=True) or {}
    created = _access_registry().create_code(data, actor="owner")
    return jsonify({"success": True, "data": created})


@business_simulation_bp.route("/access/admin/codes/<code_id>", methods=["PATCH"])
def update_business_demo_access_code(code_id: str):
    data = request.get_json(silent=True) or {}
    updated = _access_registry().update_code(code_id, data, actor="owner")
    if not updated:
        return jsonify({
            "success": False,
            "error": "Access code group not found.",
            "code": "business_demo_access_code_not_found",
        }), 404
    return jsonify({"success": True, "data": updated})


@business_simulation_bp.route("/access/admin/audit", methods=["GET"])
def list_business_demo_access_audit():
    limit = int(request.args.get("limit", "50"))
    return jsonify({
        "success": True,
        "data": {
            "audit_log": _access_registry().audit_log(limit=max(1, min(limit, 200))),
        },
    })


def _simulation_dir(simulation_id: str) -> Path:
    if not simulation_id or "/" in simulation_id or "\\" in simulation_id:
        raise ValueError("Invalid simulation_id")
    return SIMULATION_ROOT / simulation_id


def _business_dir(simulation_id: str) -> Path:
    return _simulation_dir(simulation_id) / "business"


def _default_config_path(simulation_id: str) -> Path:
    return _business_dir(simulation_id) / "business_simulation_config.json"


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def _file_digest(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _revision_ledger_path(simulation_id: str) -> Path:
    return _business_dir(simulation_id) / "scenario_revisions.json"


def _empty_revision_ledger(simulation_id: str) -> dict:
    return {
        "schema_version": "0.1",
        "ledger_type": "business_scenario_revision_ledger",
        "simulation_id": simulation_id,
        "current_revision_id": "",
        "revisions": [],
    }


def _read_revision_ledger(simulation_id: str) -> dict:
    path = _revision_ledger_path(simulation_id)
    if path.exists():
        return _read_json(path)
    return _empty_revision_ledger(simulation_id)


def _append_scenario_revision(
    simulation_id: str,
    change_type: str,
    summary: str,
    changed_paths: list[dict] | None = None,
    source: dict | None = None,
    actor: str = "MiroFish governance engine",
) -> dict:
    business_dir = _business_dir(simulation_id)
    ledger = _read_revision_ledger(simulation_id)
    revisions = ledger.setdefault("revisions", [])
    parent_revision_id = ledger.get("current_revision_id") or None
    revision = {
        "revision_id": f"rev_{len(revisions) + 1:04d}",
        "parent_revision_id": parent_revision_id,
        "change_type": change_type,
        "summary": summary,
        "actor": actor,
        "created_at": datetime.utcnow().isoformat(),
        "changed_paths": changed_paths or [],
        "source": source or {},
        "file_digests": {
            "scenario_yaml": _file_digest(business_dir / "scenario.yaml"),
            "fund_terms_yaml": _file_digest(business_dir / "fund_terms.yaml"),
            "business_simulation_config_json": _file_digest(business_dir / "business_simulation_config.json"),
        },
    }
    revisions.append(revision)
    ledger["current_revision_id"] = revision["revision_id"]
    ledger["updated_at"] = revision["created_at"]
    write_json(_revision_ledger_path(simulation_id), ledger)
    return revision


def _trim_text(value: str | None, limit: int = 1200) -> str:
    if not value:
        return ""
    return value if len(value) <= limit else f"{value[:limit]}..."


def _split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text or "")
    if not compact:
        return []
    return [
        item.strip()
        for item in re.split(r"(?<=[。！？!?])|(?<!\d)\.(?!\d)", compact)
        if item.strip()
    ]


def _type_names(items: list[dict]) -> list[str]:
    return [item.get("name", "") for item in items if item.get("name")]


def _entity_examples(ontology: dict, type_names: set[str]) -> list[str]:
    examples: list[str] = []
    for entity in ontology.get("entity_types", []):
        if entity.get("name") not in type_names:
            continue
        for example in entity.get("examples", []):
            if example and example not in examples:
                examples.append(str(example))
    return examples


def _build_project_seed(project, graph_id: str | None) -> dict:
    ontology = project.ontology or {}
    fund_examples = _entity_examples(ontology, {"InvestmentFund", "Fund"})
    gp_examples = _entity_examples(ontology, {"GeneralPartner", "CulturalInstitution", "Organization"})
    portfolio_examples = _entity_examples(ontology, {"PortfolioCompany", "TravelCompany", "Brand", "MediaPlatform", "TechProvider"})
    lp_examples = _entity_examples(ontology, {"LimitedPartner", "Investor"})
    extracted_text = ProjectManager.get_extracted_text(project.project_id) or ""

    return {
        "project_id": project.project_id,
        "project_name": project.name,
        "graph_id": graph_id or project.graph_id,
        "simulation_requirement": _trim_text(project.simulation_requirement, 4000),
        "analysis_summary": _trim_text(project.analysis_summary, 1600),
        "ontology_entity_types": _type_names(ontology.get("entity_types", [])),
        "ontology_edge_types": _type_names(ontology.get("edge_types", [])),
        "files": [item.get("filename") or item.get("original_filename") for item in project.files],
        "suggested_names": {
            "fund": f"{fund_examples[0]} Governance Fund" if fund_examples else "Fund I",
            "gp": gp_examples[0] if gp_examples else "GP",
            "lp": lp_examples[0] if lp_examples else "LP-A",
            "portfolio_company": portfolio_examples[0] if portfolio_examples else "PortfolioCo-A",
        },
        "financial_hints": _extract_financial_hints(extracted_text),
        "fund_term_hints": _extract_fund_term_hints(extracted_text),
    }


def _extract_financial_hints(text: str) -> dict:
    if not text:
        return {"source": "project_extracted_text", "amounts": [], "percentages": [], "sentences": []}
    compact = re.sub(r"\s+", " ", text)
    currency_tokens = "USD|RMB|CNY|人民币|美元|美金|¥|\\$"
    amount_units = "万|萬|亿|億|million|billion|M|B"
    amount_pattern = rf"(?:{currency_tokens})?\s?\d+(?:,\d{{3}})*(?:\.\d+)?\s?(?:{amount_units}|{currency_tokens})?"
    percentage_pattern = r"\d+(?:\.\d+)?\s?%"
    amounts = []
    for match in re.finditer(amount_pattern, compact, flags=re.IGNORECASE):
        value = match.group(0).strip()
        lower_value = value.lower()
        has_amount_signal = (
            "," in value
            or any(token in lower_value for token in ["usd", "rmb", "cny", "人民币", "美元", "美金", "million", "billion"])
            or any(token in value for token in ["¥", "$", "万", "萬", "亿", "億"])
        )
        if value and has_amount_signal and any(ch.isdigit() for ch in value) and value not in amounts:
            amounts.append(value)
        if len(amounts) >= 12:
            break
    percentages = []
    for match in re.finditer(percentage_pattern, compact):
        value = match.group(0).strip()
        if value not in percentages:
            percentages.append(value)
        if len(percentages) >= 12:
            break
    sentences = []
    for sentence in _split_sentences(compact):
        if any(keyword in sentence for keyword in ["基金", "LP", "投资", "投資", "估值", "分配", "收益", "capital", "fund"]):
            sentences.append(_trim_text(sentence.strip(), 240))
        if len(sentences) >= 6:
            break
    return {
        "source": "project_extracted_text",
        "amounts": amounts,
        "percentages": percentages,
        "sentences": sentences,
        "commit_policy": "hints_only_not_committed_to_ledger",
    }


def _extract_relevant_sentences(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    if not text:
        return []
    sentences: list[str] = []
    for sentence in _split_sentences(text):
        lowered = sentence.lower()
        if any(keyword.lower() in lowered for keyword in keywords):
            value = _trim_text(sentence.strip(), 260)
            if value and value not in sentences:
                sentences.append(value)
        if len(sentences) >= limit:
            break
    return sentences


def _extract_fund_term_hints(text: str) -> dict:
    keywords = [
        "management fee",
        "管理费",
        "管理費",
        "carry",
        "carried interest",
        "gp carry",
        "preferred return",
        "hurdle",
        "优先回报",
        "優先回報",
        "门槛收益",
        "門檻收益",
        "ic",
        "investment committee",
        "投委",
        "approval",
        "表决",
        "表決",
        "default interest",
        "default remedy",
        "违约",
        "違約",
        "cure period",
        "补救期",
        "補救期",
        "reserve",
        "reserve account",
        "储备",
        "儲備",
        "准备金",
        "準備金",
        "audit",
        "materiality",
        "审计",
        "審計",
        "重大性",
    ]
    sentences = _extract_relevant_sentences(text, keywords, limit=10)
    percentages = []
    amounts = []
    days = []
    for sentence in sentences:
        for match in re.finditer(r"\d+(?:\.\d+)?\s?%", sentence):
            value = match.group(0).strip()
            if value not in percentages:
                percentages.append(value)
        for match in re.finditer(r"\d+(?:\.\d+)?\s?(?:days?|日|天)", sentence, flags=re.IGNORECASE):
            value = match.group(0).strip()
            if value not in days:
                days.append(value)
        for raw in re.findall(r"(?:USD|RMB|CNY|人民币|美元|美金|¥|\$)?\s?\d+(?:,\d{3})*(?:\.\d+)?\s?(?:万|萬|亿|億|million|billion|M|B|USD|RMB|CNY|人民币|美元|美金)?", sentence, flags=re.IGNORECASE):
            parsed = _parse_amount_candidate(raw)
            if parsed and parsed not in amounts:
                amounts.append(parsed)
    return {
        "source": "project_extracted_text",
        "sentences": sentences,
        "percentages": percentages[:12],
        "amounts": amounts[:12],
        "days": days[:12],
        "commit_policy": "hints_only_not_committed_to_rules",
    }


def _parse_amount_candidate(value: str) -> dict | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    number_match = re.search(r"\d+(?:,\d{3})*(?:\.\d+)?", cleaned)
    if not number_match:
        return None

    number = float(number_match.group(0).replace(",", ""))
    lower_value = cleaned.lower()
    multiplier = 1.0
    unit = "absolute"
    if "億" in cleaned or "亿" in cleaned:
        multiplier = 100_000_000.0
        unit = "yi"
    elif "萬" in cleaned or "万" in cleaned:
        multiplier = 10_000.0
        unit = "wan"
    elif "billion" in lower_value or re.search(r"\d\s?b\b", lower_value):
        multiplier = 1_000_000_000.0
        unit = "billion"
    elif "million" in lower_value or re.search(r"\d\s?m\b", lower_value):
        multiplier = 1_000_000.0
        unit = "million"

    currency = "USD"
    if any(token in cleaned for token in ["¥", "人民币"]) or "rmb" in lower_value or "cny" in lower_value:
        currency = "CNY"

    return {
        "raw": cleaned,
        "normalized_amount": round(number * multiplier, 2),
        "currency": currency,
        "unit": unit,
    }


def _parse_percentage_candidate(value: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group(0))


def _parse_days_candidate(value: str) -> int | None:
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return None
    return int(float(match.group(0)))


def _choose_capital_call_rate(percentages: list[str]) -> tuple[float, str | None]:
    parsed_pairs = [
        (raw, parsed_value)
        for raw in percentages
        for parsed_value in [_parse_percentage_candidate(raw)]
        if parsed_value is not None
    ]
    for raw, parsed_value in parsed_pairs:
        if abs(parsed_value - 10) < 0.001:
            return parsed_value / 100, raw
    return 0.10, None


def _build_proposed_financial_plan(financial_plan: dict, financial_hints: dict) -> dict:
    parsed_amounts = [
        parsed
        for raw in financial_hints.get("amounts", [])
        for parsed in [_parse_amount_candidate(raw)]
        if parsed
    ]
    percentages = financial_hints.get("percentages", [])
    capital_call_rate, source_percentage = _choose_capital_call_rate(percentages)

    proposals = {}
    warnings = [
        "Proposal is generated from extracted project text and is not committed to the ledger.",
        "A human approval step is required before replacing the deterministic financial_plan.",
    ]

    if parsed_amounts:
        commitment_candidate = max(parsed_amounts, key=lambda item: item["normalized_amount"])
        commitment = commitment_candidate["normalized_amount"]
        call_amount = round(commitment * capital_call_rate, 2)
        investment_amount = round(call_amount * 0.75, 2)
        liquidity_proceeds = round(investment_amount * 1.60, 2)
        distribution_amount = round(liquidity_proceeds * 0.9583333333, 2)
        proposals = {
            "lp_commitment": {
                "value": commitment,
                "source_amount": commitment_candidate["raw"],
                "confidence": "medium",
                "reason": "Largest extracted amount is treated as possible fund/LP commitment.",
            },
            "capital_call_amount": {
                "value": call_amount,
                "source_percentage": source_percentage or "default_10%",
                "confidence": "medium" if source_percentage else "low",
                "reason": "Capital call proposal is derived from extracted percentage or the default 10% call rate.",
            },
            "investment_amount": {
                "value": investment_amount,
                "confidence": "low",
                "reason": "Derived as 75% of proposed called capital, matching the simulator baseline assumption.",
            },
            "liquidity_proceeds": {
                "value": liquidity_proceeds,
                "confidence": "low",
                "reason": "Derived as 1.6x proposed invested capital until a confirmed exit assumption exists.",
            },
            "distribution_amount": {
                "value": distribution_amount,
                "confidence": "low",
                "reason": "Derived from proposed liquidity proceeds while preserving a reserve.",
            },
        }
    else:
        warnings.append("No parseable amount candidates were found in the source project text.")

    return {
        "source": "financial_hints_proposal",
        "status": "not_committed_to_ledger",
        "commit_policy": "proposal_only_requires_user_confirmation",
        "base_plan_source": financial_plan.get("source", ""),
        "base_plan_snapshot": financial_plan,
        "parsed_amounts": parsed_amounts,
        "percentage_candidates": percentages,
        "proposals": proposals,
        "warnings": warnings,
    }


def _sentence_has(sentence: str, keywords: list[str]) -> bool:
    lowered = sentence.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _first_percentage_from_sentence(sentence: str, min_value: float | None = None, max_value: float | None = None) -> tuple[float, str] | None:
    for match in re.finditer(r"\d+(?:\.\d+)?\s?%", sentence):
        raw = match.group(0).strip()
        parsed = _parse_percentage_candidate(raw)
        if parsed is None:
            continue
        if min_value is not None and parsed < min_value:
            continue
        if max_value is not None and parsed > max_value:
            continue
        return parsed / 100, raw
    return None


def _first_days_from_sentence(sentence: str) -> tuple[int, str] | None:
    for match in re.finditer(r"\d+(?:\.\d+)?\s?(?:days?|日|天)", sentence, flags=re.IGNORECASE):
        raw = match.group(0).strip()
        parsed = _parse_days_candidate(raw)
        if parsed is not None:
            return parsed, raw
    return None


def _first_amount_from_sentence(sentence: str) -> dict | None:
    amount_pattern = r"(?:USD|RMB|CNY|人民币|美元|美金|¥|\$)?\s?\d+(?:,\d{3})*(?:\.\d+)?\s?(?:万|萬|亿|億|million|billion|M|B|USD|RMB|CNY|人民币|美元|美金)?"
    for match in re.finditer(amount_pattern, sentence, flags=re.IGNORECASE):
        parsed = _parse_amount_candidate(match.group(0))
        if parsed:
            return parsed
    return None


def _proposal(clause_type: str, parameters: dict, evidence: str, confidence: str = "medium") -> dict:
    return {
        "clause_type": clause_type,
        "parameters": parameters,
        "evidence": evidence,
        "confidence": confidence,
    }


def _build_proposed_fund_terms(fund_terms: dict, fund_term_hints: dict) -> dict:
    sentences = fund_term_hints.get("sentences", [])
    proposals: dict[str, dict] = {}
    warnings = [
        "Proposal is generated from extracted project text and is not committed to governance rules.",
        "A human approval step is required before replacing deterministic fund_terms clauses.",
    ]

    for sentence in sentences:
        if "management_fee" not in proposals and _sentence_has(sentence, ["management fee", "管理费", "管理費"]):
            percentage = _first_percentage_from_sentence(sentence, max_value=10)
            if percentage:
                proposals["management_fee"] = _proposal(
                    "management_fee",
                    {"annual_rate": percentage[0], "basis": "committed_capital", "period_months": 3},
                    sentence,
                )

        if "voting_threshold" not in proposals and _sentence_has(sentence, ["ic", "investment committee", "投委", "approval", "表决", "表決"]):
            percentage = _first_percentage_from_sentence(sentence, min_value=50, max_value=100)
            if percentage:
                proposals["voting_threshold"] = _proposal(
                    "voting_threshold",
                    {"matter": "investment_approval", "threshold_percent": round(percentage[0] * 100, 2)},
                    sentence,
                )

        if "preferred_return" not in proposals and _sentence_has(sentence, ["preferred return", "hurdle", "优先回报", "優先回報", "门槛收益", "門檻收益"]):
            percentage = _first_percentage_from_sentence(sentence, max_value=25)
            if percentage:
                proposals["preferred_return"] = _proposal(
                    "waterfall_rule",
                    {"preferred_return_rate": percentage[0], "preferred_return_months": 12},
                    sentence,
                )

        if "gp_carry" not in proposals and _sentence_has(sentence, ["carry", "carried interest", "gp carry", "超额收益", "超額收益"]):
            percentage = _first_percentage_from_sentence(sentence, max_value=50)
            if percentage:
                proposals["gp_carry"] = _proposal(
                    "waterfall_rule",
                    {"gp_carry": percentage[0], "lp_profit_split": round(1 - percentage[0], 4)},
                    sentence,
                )

        if "default_remedies" not in proposals and _sentence_has(sentence, ["default interest", "default remedy", "违约", "違約"]):
            percentage = _first_percentage_from_sentence(sentence, max_value=50)
            days = _first_days_from_sentence(sentence)
            params = {}
            if percentage:
                params["default_interest_annual_rate"] = percentage[0]
                params["default_interest_days"] = 30
            if days:
                params["cure_period_days"] = days[0]
            if params:
                params.setdefault("suspend_voting_rights", True)
                params.setdefault("block_new_deployments", True)
                proposals["default_remedies"] = _proposal("default_remedies", params, sentence)

        if "reserve_account" not in proposals and _sentence_has(sentence, ["reserve", "reserve account", "储备", "儲備", "准备金", "準備金"]):
            amount = _first_amount_from_sentence(sentence)
            percentage = _first_percentage_from_sentence(sentence, max_value=30)
            params = {"review_before_distribution": True}
            if amount:
                params["minimum_cash"] = amount["normalized_amount"]
            if percentage:
                params["rate_of_called_capital"] = percentage[0]
            if "minimum_cash" in params or "rate_of_called_capital" in params:
                proposals["reserve_account"] = _proposal("reserve_account", params, sentence)

        if "audit_review" not in proposals and _sentence_has(sentence, ["audit", "materiality", "审计", "審計", "重大性"]):
            amount = _first_amount_from_sentence(sentence)
            params = {
                "required_checks": [
                    "ledger_balanced",
                    "reserve_account_reviewed",
                    "waterfall_rule_applied",
                ]
            }
            if amount:
                params["materiality_threshold"] = amount["normalized_amount"]
            proposals["audit_review"] = _proposal("audit_review", params, sentence)

    if not proposals:
        warnings.append("No parseable governance term candidates were found in the source project text.")

    return {
        "source": "fund_term_hints_proposal",
        "status": "not_committed_to_rules",
        "commit_policy": "proposal_only_requires_user_confirmation",
        "base_terms_snapshot": {
            "management_fee": _clause_parameters_from_terms(fund_terms, "management_fee"),
            "default_remedies": _clause_parameters_from_terms(fund_terms, "default_remedies"),
            "reserve_account": _clause_parameters_from_terms(fund_terms, "reserve_account"),
            "voting_threshold": _clause_parameters_from_terms(fund_terms, "voting_threshold"),
            "waterfall_rule": _clause_parameters_from_terms(fund_terms, "waterfall_rule"),
            "audit_review": _clause_parameters_from_terms(fund_terms, "audit_review"),
        },
        "hints": fund_term_hints,
        "proposals": proposals,
        "warnings": warnings,
    }


def _attach_project_seed(config: dict, scenario: dict, project_seed: dict) -> None:
    config["source_project"] = project_seed
    scenario["source_project"] = project_seed
    scenario.setdefault("scenario", {})["source_project_id"] = project_seed["project_id"]
    scenario["scenario"]["source_graph_id"] = project_seed.get("graph_id") or ""


def _build_financial_plan(fund_terms: dict, project_seed: dict) -> dict:
    lp = fund_terms.get("parties", {}).get("lps", [{}])[0]
    commitment = float(lp.get("commitment", 10_000_000))
    capital_call_amount = round(commitment * 0.10, 2)
    investment_amount = round(capital_call_amount * 0.75, 2)
    liquidity_proceeds = round(investment_amount * 1.60, 2)
    distribution_amount = round(liquidity_proceeds * 0.9583333333, 2)
    follow_on_reserve_amount = round(investment_amount * 0.20, 2)
    return {
        "source": "fund_terms_and_project_seed",
        "lp_commitment": commitment,
        "capital_call_amount": capital_call_amount,
        "investment_amount": investment_amount,
        "liquidity_proceeds": liquidity_proceeds,
        "distribution_amount": distribution_amount,
        "follow_on_reserve_amount": follow_on_reserve_amount,
        "assumptions": [
            "capital_call_amount = 10% of LP commitment",
            "investment_amount = 75% of called capital",
            "liquidity_proceeds = 1.6x invested capital",
            "distribution_amount keeps reserve cash after realization",
            "follow_on_reserve_amount = 20% of invested capital for next-round readiness",
        ],
        "project_id": project_seed.get("project_id"),
    }


def _build_planned_events(project_seed: dict, financial_plan: dict) -> list[dict]:
    names = project_seed.get("suggested_names", {})
    portfolio_slug = "portco_a"
    return [
        {
            "simulation_time": "2026-02-15",
            "event_type": "DealEvaluation",
            "payload": {
                "deal_id": f"deal_{portfolio_slug}",
                "portfolio_company_id": portfolio_slug,
                "generated_from": "project_seed",
                "candidate_name": names.get("portfolio_company", "PortfolioCo-A"),
            },
        },
        {
            "simulation_time": "2026-02-20",
            "event_type": "ComplianceCheck",
            "payload": {"deal_id": f"deal_{portfolio_slug}", "generated_from": "project_seed"},
        },
        {
            "simulation_time": "2026-03-01",
            "event_type": "ICMeeting",
            "payload": {
                "deal_id": f"deal_{portfolio_slug}",
                "approval_threshold_percent": 66.67,
                "generated_from": "project_seed",
            },
        },
        {
            "simulation_time": "2026-03-05",
            "event_type": "ManagementFeePayment",
            "payload": {"period": "Q1", "generated_from": "project_seed"},
        },
        {
            "simulation_time": "2026-03-10",
            "event_type": "InvestmentExecution",
            "payload": {
                "deal_id": f"deal_{portfolio_slug}",
                "amount": financial_plan["investment_amount"],
                "generated_from": "project_seed",
            },
        },
        {
            "simulation_time": "2026-04-15",
            "event_type": "QuarterlyReport",
            "payload": {"quarter": "Q1", "generated_from": "project_seed"},
        },
        {
            "simulation_time": "2026-07-15",
            "event_type": "QuarterlyReport",
            "payload": {"quarter": "Q2", "generated_from": "project_seed"},
        },
        {
            "simulation_time": "2026-08-01",
            "event_type": "FollowOnDiscussion",
            "payload": {"portfolio_company_id": portfolio_slug, "generated_from": "project_seed"},
        },
        {
            "simulation_time": "2026-08-05",
            "event_type": "FollowOnReserveReview",
            "payload": {
                "portfolio_company_id": portfolio_slug,
                "target_reserve": financial_plan.get("follow_on_reserve_amount"),
                "generated_from": "project_seed",
            },
        },
        {
            "simulation_time": "2026-10-01",
            "event_type": "LiquidityEvent",
            "payload": {
                "portfolio_company_id": portfolio_slug,
                "proceeds": financial_plan["liquidity_proceeds"],
                "generated_from": "project_seed",
            },
        },
        {
            "simulation_time": "2026-10-03",
            "event_type": "ReserveAccountReview",
            "payload": {"planned_distribution": financial_plan["distribution_amount"], "generated_from": "project_seed"},
        },
        {
            "simulation_time": "2026-10-05",
            "event_type": "Distribution",
            "payload": {"amount": financial_plan["distribution_amount"], "generated_from": "project_seed"},
        },
        {
            "simulation_time": "2026-11-01",
            "event_type": "FollowOnCapitalCall",
            "payload": {
                "amount": financial_plan.get("follow_on_reserve_amount"),
                "purpose": "follow_on_reserve_top_up",
                "generated_from": "project_seed",
            },
        },
        {
            "simulation_time": "2026-12-15",
            "event_type": "AuditReview",
            "payload": {"generated_from": "project_seed"},
        },
    ]


def _financial_plan_from_proposal(proposed_financial_plan: dict, project_id: str | None = None) -> dict:
    proposals = proposed_financial_plan.get("proposals", {})
    required = [
        "lp_commitment",
        "capital_call_amount",
        "investment_amount",
        "liquidity_proceeds",
        "distribution_amount",
    ]
    missing = [key for key in required if key not in proposals or "value" not in proposals[key]]
    if missing:
        raise ValueError(f"Cannot commit proposal; missing values: {', '.join(missing)}")

    return {
        "source": "committed_proposed_financial_plan",
        "lp_commitment": float(proposals["lp_commitment"]["value"]),
        "capital_call_amount": float(proposals["capital_call_amount"]["value"]),
        "investment_amount": float(proposals["investment_amount"]["value"]),
        "liquidity_proceeds": float(proposals["liquidity_proceeds"]["value"]),
        "distribution_amount": float(proposals["distribution_amount"]["value"]),
        "follow_on_reserve_amount": round(float(proposals["investment_amount"]["value"]) * 0.20, 2),
        "assumptions": [
            "Committed from proposed_financial_plan after explicit approval.",
            f"lp_commitment source amount: {proposals['lp_commitment'].get('source_amount', 'unknown')}",
            f"capital_call source percentage: {proposals['capital_call_amount'].get('source_percentage', 'unknown')}",
            "follow_on_reserve_amount = 20% of committed investment amount for next-round readiness.",
        ],
        "project_id": project_id,
        "committed_at": datetime.utcnow().isoformat(),
    }


def _lpa_clauses(fund_terms: dict) -> list[dict]:
    contracts = fund_terms.setdefault("contracts", [])
    if not contracts:
        contracts.append({
            "id": "lpa_fund_i",
            "type": "LPA",
            "effective_date": "2026-01-01",
            "parties": ["fund_i", "gp", "lp_a"],
            "clauses": [],
        })
    return contracts[0].setdefault("clauses", [])


def _clause_parameters_from_terms(fund_terms: dict, clause_type: str) -> dict:
    for clause in _lpa_clauses(fund_terms):
        if clause.get("type") == clause_type:
            return clause.setdefault("parameters", {})
    return {}


def _set_clause_parameters(fund_terms: dict, clause_type: str, parameters: dict) -> None:
    clauses = _lpa_clauses(fund_terms)
    for clause in clauses:
        if clause.get("type") == clause_type:
            clause.setdefault("parameters", {}).update(parameters)
            return
    clauses.append({
        "id": f"clause_{clause_type}",
        "type": clause_type,
        "parameters": parameters,
    })


def _sync_committed_fund_terms(fund_terms: dict, scenario: dict, proposed_fund_terms: dict) -> dict:
    proposals = proposed_fund_terms.get("proposals", {})
    if not proposals:
        raise ValueError("Cannot commit proposal; no proposed fund terms found")

    committed: dict[str, dict] = {}
    for proposal_id, proposal in proposals.items():
        clause_type = proposal.get("clause_type")
        parameters = proposal.get("parameters", {})
        if not clause_type or not parameters:
            continue
        _set_clause_parameters(fund_terms, clause_type, parameters)
        committed[proposal_id] = {
            "clause_type": clause_type,
            "parameters": parameters,
            "evidence": proposal.get("evidence", ""),
            "confidence": proposal.get("confidence", "unknown"),
        }

    if not committed:
        raise ValueError("Cannot commit proposal; proposed fund terms did not include parameters")

    committed_at = datetime.utcnow().isoformat()
    scenario["proposed_fund_terms"] = proposed_fund_terms
    scenario["proposed_fund_terms"]["status"] = "committed_to_rules"
    scenario["proposed_fund_terms"]["committed_at"] = committed_at
    scenario["event_generation"] = scenario.get("event_generation", {})
    scenario["event_generation"]["fund_terms_source"] = "committed_proposed_fund_terms"
    return {
        "source": "committed_proposed_fund_terms",
        "committed_at": committed_at,
        "committed": committed,
    }


def _sync_committed_financial_plan(fund_terms: dict, scenario: dict, financial_plan: dict) -> None:
    fund_terms.setdefault("parties", {}).setdefault("lps", [{}])[0]["commitment"] = financial_plan["lp_commitment"]

    for event in scenario.get("initial_events", []):
        if event.get("event_type") == "InitialCapitalCall":
            event.setdefault("payload", {})["amount"] = financial_plan["capital_call_amount"]

    project_seed = scenario.get("source_project") or {}
    scenario["financial_plan"] = financial_plan
    scenario["planned_events"] = _build_planned_events(project_seed, financial_plan)


def _coerce_patch_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in {"true", "false"}:
            return stripped.lower() == "true"
        if re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
            return float(stripped)
        return stripped
    if isinstance(value, list):
        return value
    return value


def _normalize_scenario_patch(data: dict) -> dict:
    raw_patch = data.get("patch") if isinstance(data.get("patch"), dict) else data
    financial_raw = raw_patch.get("financial_plan") or {}
    fund_terms_raw = raw_patch.get("fund_terms") or {}
    if not isinstance(financial_raw, dict) or not isinstance(fund_terms_raw, dict):
        raise ValueError("scenario patch must include object values for financial_plan and fund_terms")

    patch = {"financial_plan": {}, "fund_terms": {}}
    for field, value in financial_raw.items():
        if field not in EDITABLE_FINANCIAL_FIELDS:
            raise ValueError(f"Unsupported financial_plan patch field: {field}")
        patch["financial_plan"][field] = _coerce_patch_value(value)

    for clause_type, parameters in fund_terms_raw.items():
        if clause_type not in EDITABLE_FUND_TERM_FIELDS:
            raise ValueError(f"Unsupported fund_terms patch clause: {clause_type}")
        if not isinstance(parameters, dict):
            raise ValueError(f"fund_terms.{clause_type} patch must be an object")
        allowed_fields = EDITABLE_FUND_TERM_FIELDS[clause_type]
        patch["fund_terms"][clause_type] = {}
        for field, value in parameters.items():
            if field not in allowed_fields:
                raise ValueError(f"Unsupported fund_terms.{clause_type} patch field: {field}")
            patch["fund_terms"][clause_type][field] = _coerce_patch_value(value)

    return patch


def _current_editable_values(fund_terms: dict, scenario: dict) -> dict:
    financial_plan = scenario.get("financial_plan") or {}
    values = {
        "financial_plan": {
            key: financial_plan.get(key)
            for key in EDITABLE_FINANCIAL_FIELDS
            if key in financial_plan
        },
        "fund_terms": {},
    }
    if "lp_commitment" not in values["financial_plan"]:
        values["financial_plan"]["lp_commitment"] = fund_terms.get("parties", {}).get("lps", [{}])[0].get("commitment")

    for clause_type in EDITABLE_FUND_TERM_FIELDS:
        current = _clause_parameters_from_terms(fund_terms, clause_type)
        values["fund_terms"][clause_type] = {
            key: current.get(key)
            for key in EDITABLE_FUND_TERM_FIELDS[clause_type]
            if key in current
        }
    return values


def _apply_patch_to_snapshot(snapshot: dict, patch: dict) -> dict:
    after = json.loads(json.dumps(snapshot, ensure_ascii=False))
    after.setdefault("financial_plan", {}).update(patch.get("financial_plan", {}))
    for clause_type, parameters in patch.get("fund_terms", {}).items():
        after.setdefault("fund_terms", {}).setdefault(clause_type, {}).update(parameters)
    return after


def _diff_snapshots(before, after, path: str = "") -> list[dict]:
    changes: list[dict] = []
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted(set(before.keys()) | set(after.keys()))
        for key in keys:
            next_path = f"{path}.{key}" if path else key
            changes.extend(_diff_snapshots(before.get(key), after.get(key), next_path))
        return changes
    if before != after:
        changes.append({"path": path, "before": before, "after": after})
    return changes


def _scenario_patch_impact_preview(after_values: dict) -> dict:
    financial_plan = after_values.get("financial_plan", {})
    terms = after_values.get("fund_terms", {})
    management_fee = terms.get("management_fee", {})
    reserve = terms.get("reserve_account", {})
    lp_commitment = float(financial_plan.get("lp_commitment") or 0)
    capital_call = float(financial_plan.get("capital_call_amount") or 0)
    investment = float(financial_plan.get("investment_amount") or 0)
    liquidity = float(financial_plan.get("liquidity_proceeds") or 0)
    distribution = float(financial_plan.get("distribution_amount") or 0)
    annual_fee_rate = float(management_fee.get("annual_rate") or 0)
    fee_months = float(management_fee.get("period_months") or 3)
    fee_basis = management_fee.get("basis", "committed_capital")
    fee_basis_amount = lp_commitment if fee_basis == "committed_capital" else capital_call
    management_fee_amount = round(fee_basis_amount * annual_fee_rate * fee_months / 12, 2)
    reserve_required = round(max(
        float(reserve.get("minimum_cash") or 0),
        capital_call * float(reserve.get("rate_of_called_capital") or 0),
    ), 2)
    projected_after_distribution = round(capital_call - management_fee_amount - investment + liquidity - distribution, 2)
    reserve_shortfall = round(max(reserve_required - projected_after_distribution, 0), 2)
    return {
        "capital_called": capital_call,
        "investment_amount": investment,
        "liquidity_proceeds": liquidity,
        "distribution_amount": distribution,
        "management_fee_amount": management_fee_amount,
        "reserve_required": reserve_required,
        "projected_cash_after_distribution": projected_after_distribution,
        "reserve_shortfall": reserve_shortfall,
        "reserve_compliant": reserve_shortfall == 0,
    }


def _build_scenario_patch_preview(simulation_id: str, fund_terms: dict, scenario: dict, patch: dict, status: str = "preview") -> dict:
    before = _current_editable_values(fund_terms, scenario)
    after = _apply_patch_to_snapshot(before, patch)
    changes = _diff_snapshots(before, after)
    return {
        "schema_version": "0.1",
        "simulation_id": simulation_id,
        "patch_type": "editable_scenario_terms_workspace",
        "status": status,
        "created_at": datetime.utcnow().isoformat(),
        "commit_policy": "manual_patch_requires_explicit_commit_before_rerun",
        "patch": patch,
        "changed_paths": changes,
        "rerun_required": bool(changes),
        "before": before,
        "after": after,
        "impact_preview": _scenario_patch_impact_preview(after),
    }


def _apply_scenario_patch(simulation_id: str, fund_terms: dict, scenario: dict, patch: dict) -> dict:
    preview = _build_scenario_patch_preview(simulation_id, fund_terms, scenario, patch, status="committed")
    if not preview["changed_paths"]:
        return preview

    financial_patch = patch.get("financial_plan") or {}
    if financial_patch:
        financial_plan = dict(scenario.get("financial_plan") or _build_financial_plan(fund_terms, scenario.get("source_project") or {}))
        financial_plan.update(financial_patch)
        financial_plan["source"] = "manual_scenario_patch"
        financial_plan["patched_at"] = preview["created_at"]
        assumptions = list(financial_plan.get("assumptions") or [])
        assumptions.append("Manual scenario patch committed through Editable Scenario / Terms Workspace.")
        financial_plan["assumptions"] = assumptions
        _sync_committed_financial_plan(fund_terms, scenario, financial_plan)

    for clause_type, parameters in (patch.get("fund_terms") or {}).items():
        _set_clause_parameters(fund_terms, clause_type, parameters)

    scenario["manual_scenario_patch"] = {
        "schema_version": preview["schema_version"],
        "status": "committed",
        "patch_type": preview["patch_type"],
        "committed_at": preview["created_at"],
        "commit_policy": preview["commit_policy"],
        "patch": patch,
        "changed_paths": preview["changed_paths"],
        "impact_preview": preview["impact_preview"],
    }
    scenario.setdefault("event_generation", {})["scenario_patch_source"] = "manual_editable_workspace"
    return preview


def _customize_business_inputs(fund_terms: dict, scenario: dict, project_seed: dict) -> None:
    names = project_seed.get("suggested_names", {})
    fund_name = names.get("fund") or "Fund I"
    gp_name = names.get("gp") or "GP"
    lp_name = names.get("lp") or "LP-A"
    portfolio_name = names.get("portfolio_company") or "PortfolioCo-A"

    fund_terms.setdefault("fund", {})["name"] = fund_name
    fund_terms.setdefault("parties", {}).setdefault("gps", [{}])[0]["name"] = gp_name
    fund_terms.setdefault("parties", {}).setdefault("lps", [{}])[0]["name"] = lp_name
    fund_terms.setdefault("parties", {}).setdefault("portfolio_companies", [{}])[0]["name"] = portfolio_name
    fund_terms["project_seed"] = {
        "project_id": project_seed.get("project_id"),
        "graph_id": project_seed.get("graph_id"),
        "simulation_requirement": project_seed.get("simulation_requirement", ""),
        "suggested_names": names,
    }
    financial_plan = _build_financial_plan(fund_terms, project_seed)
    proposed_financial_plan = _build_proposed_financial_plan(
        financial_plan,
        project_seed.get("financial_hints", {}),
    )
    proposed_fund_terms = _build_proposed_fund_terms(
        fund_terms,
        project_seed.get("fund_term_hints", {}),
    )

    scenario.setdefault("scenario", {})["name"] = f"{fund_name} 12-month governance operations"
    scenario["scenario"]["project_requirement"] = project_seed.get("simulation_requirement", "")
    scenario["financial_plan"] = financial_plan
    scenario["proposed_financial_plan"] = proposed_financial_plan
    scenario["proposed_fund_terms"] = proposed_fund_terms
    scenario["event_generation"] = {
        "source": "project_seed",
        "strategy": "deterministic_fund_governance_plan_v1",
        "derived_from": {
            "project_id": project_seed.get("project_id"),
            "ontology_entity_types": project_seed.get("ontology_entity_types", []),
        },
    }
    scenario["planned_events"] = _build_planned_events(project_seed, financial_plan)


def _create_simulation_from_template(simulation_id: str, project, graph_id: str | None) -> dict:
    sim_dir = _simulation_dir(simulation_id)
    business_dir = _business_dir(simulation_id)
    if sim_dir.exists():
        raise FileExistsError(f"Simulation already exists: {simulation_id}")

    if not DEMO_BUSINESS_DIR.exists():
        raise FileNotFoundError(f"Business simulation template not found: {DEMO_BUSINESS_DIR}")

    now = datetime.utcnow().isoformat()
    business_dir.mkdir(parents=True, exist_ok=True)

    fund_terms = load_structured_file(DEMO_BUSINESS_DIR / "fund_terms.yaml")
    scenario = load_structured_file(DEMO_BUSINESS_DIR / "scenario.yaml")
    agent_profiles = load_structured_file(DEMO_BUSINESS_DIR / "agent_profiles.yaml")
    config = load_structured_file(DEMO_BUSINESS_DIR / "business_simulation_config.json")
    project_seed = _build_project_seed(project, graph_id)
    _attach_project_seed(config, scenario, project_seed)
    _customize_business_inputs(fund_terms, scenario, project_seed)

    config.update({
        "engine_type": "business_governance",
        "simulation_id": simulation_id,
        "project_id": project.project_id,
        "graph_id": graph_id or project.graph_id or "",
    })

    state = {
        "simulation_id": simulation_id,
        "project_id": project.project_id,
        "project_name": project.name,
        "graph_id": graph_id or project.graph_id,
        "engine_type": "business_governance",
        "status": "ready",
        "simulation_requirement": _trim_text(project.simulation_requirement, 4000),
        "created_at": now,
    }
    run_state = {
        "simulation_id": simulation_id,
        "engine_type": "business_governance",
        "runner_status": "idle",
        "current_round": 0,
        "business_events_count": 0,
        "ledger_entries_count": 0,
        "updated_at": now,
    }

    write_json(sim_dir / "state.json", state)
    write_json(sim_dir / "run_state.json", run_state)
    _write_yaml(business_dir / "fund_terms.yaml", fund_terms)
    _write_yaml(business_dir / "scenario.yaml", scenario)
    _write_yaml(business_dir / "agent_profiles.yaml", agent_profiles)
    write_json(business_dir / "business_simulation_config.json", config)
    initial_revision = _append_scenario_revision(
        simulation_id,
        change_type="initial_template",
        summary="Created business governance simulation inputs from MiroFish project seed.",
        source={
            "project_id": project.project_id,
            "graph_id": graph_id or project.graph_id or "",
            "engine_type": "business_governance",
        },
    )

    return {
        "simulation_id": simulation_id,
        "project_id": project.project_id,
        "project_name": project.name,
        "graph_id": graph_id or project.graph_id,
        "engine_type": "business_governance",
        "status": "ready",
        "source_project": project_seed,
        "current_revision_id": initial_revision["revision_id"],
        "config_path": str(business_dir / "business_simulation_config.json"),
        "run_endpoint": "/api/business-simulation/run",
    }


@business_simulation_bp.route("/demo", methods=["GET"])
def get_demo_business_simulation():
    """Return the bundled smoke demo location and latest status."""
    simulation_id = "demo_business"
    run_state_path = _simulation_dir(simulation_id) / "run_state.json"
    run_state = _read_json(run_state_path) if run_state_path.exists() else None

    return jsonify({
        "success": True,
        "data": {
            "simulation_id": simulation_id,
            "engine_type": "business_governance",
            "config_path": str(_default_config_path(simulation_id)),
            "run_state": run_state,
            "run_endpoint": "/api/business-simulation/run",
        }
    })


def _business_history_item(simulation_id: str) -> dict | None:
    sim_dir = _simulation_dir(simulation_id)
    business_dir = _business_dir(simulation_id)
    config_path = business_dir / "business_simulation_config.json"
    if not config_path.exists():
        return None

    state_path = sim_dir / "state.json"
    run_state_path = sim_dir / "run_state.json"
    report_context_path = business_dir / "report_context.json"

    state = _read_json(state_path) if state_path.exists() else {}
    run_state = _read_json(run_state_path) if run_state_path.exists() else {}
    config = _read_json(config_path)
    report_context = _read_json(report_context_path) if report_context_path.exists() else {}
    source_project = report_context.get("source_project") or config.get("source_project") or state.get("source_project") or {}

    current_round = int(run_state.get("current_round") or run_state.get("business_events_count") or 0)
    total_rounds = current_round if run_state.get("runner_status") == "completed" else 0
    files = [{"filename": name} for name in (source_project.get("files") or [])[:3] if name]
    report_path = business_dir / "business_report.md"

    return {
        "simulation_id": simulation_id,
        "project_id": state.get("project_id") or config.get("project_id") or source_project.get("project_id", ""),
        "project_name": state.get("project_name") or source_project.get("project_name", "Business Governance"),
        "graph_id": state.get("graph_id") or config.get("graph_id") or source_project.get("graph_id", ""),
        "engine_type": "business_governance",
        "simulation_requirement": state.get("simulation_requirement") or source_project.get("simulation_requirement", ""),
        "status": state.get("status", "ready"),
        "runner_status": run_state.get("runner_status", "idle"),
        "current_round": current_round,
        "total_rounds": total_rounds,
        "business_events_count": run_state.get("business_events_count", current_round),
        "ledger_entries_count": run_state.get("ledger_entries_count", 0),
        "files": files,
        "report_id": None,
        "business_report_available": report_path.exists(),
        "created_at": state.get("created_at") or run_state.get("updated_at", ""),
        "updated_at": run_state.get("updated_at") or state.get("created_at", ""),
        "version": "business-governance-0.1",
    }


@business_simulation_bp.route("/history", methods=["GET"])
def get_business_simulation_history():
    """Return business-governance simulations for the MiroFish history UI."""
    try:
        limit = request.args.get("limit", 20, type=int)
        items: list[dict] = []
        if SIMULATION_ROOT.exists():
            for path in SIMULATION_ROOT.iterdir():
                if not path.is_dir():
                    continue
                try:
                    item = _business_history_item(path.name)
                    if item:
                        items.append(item)
                except Exception as exc:
                    logger.warning("Skipping business simulation history item %s: %s", path.name, exc)

        items.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
        return jsonify({"success": True, "data": items[:limit], "count": min(len(items), limit)})
    except Exception as e:
        logger.error("Business simulation history failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/create", methods=["POST"])
def create_business_simulation():
    """Create a business-governance simulation from a graph project.

    This is the OASIS-slot replacement entrypoint used by the frontend after
    ontology/graph construction. The first MVP seeds fund terms from the
    bundled business template, then stores the calling project and graph IDs so
    downstream extraction can specialize the world from the project graph.
    """
    try:
        data = request.get_json(silent=True) or {}
        project_id = data.get("project_id")
        graph_id = data.get("graph_id")
        simulation_id = data.get("simulation_id") or f"bus_{uuid4().hex[:12]}"

        if not project_id:
            return jsonify({"success": False, "error": "project_id is required"}), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": f"Project not found: {project_id}"}), 404

        payload = _create_simulation_from_template(simulation_id, project, graph_id or project.graph_id)
        return jsonify({"success": True, "data": payload})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except FileExistsError as e:
        return jsonify({"success": False, "error": str(e)}), 409
    except Exception as e:
        logger.error("Business simulation creation failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/run", methods=["POST"])
def run_business_simulation():
    """Run a business-governance simulation synchronously.

    Request:
        {
            "simulation_id": "demo_business"  // optional, defaults to demo
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        simulation_id = data.get("simulation_id", "demo_business")
        config_path = _default_config_path(simulation_id)

        if not config_path.exists():
            return jsonify({
                "success": False,
                "error": f"Business simulation config not found: {config_path}"
            }), 404

        logger.info("Running business-governance simulation: %s", simulation_id)
        result = BusinessSimulationEngine(config_path).run()

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": result.state.simulation_id,
                "engine_type": "business_governance",
                "status": "completed",
                "events": result.event_count,
                "ledger_entries": result.ledger_entry_count,
                "decisions": result.decision_count,
                "rule_executions": result.rule_execution_count,
                "ledger_balanced": result.state.ledger_summary.get("balanced", False),
                "outputs": {
                    "business_dir": str(_business_dir(simulation_id)),
                    "event_log": str(_business_dir(simulation_id) / "event_log.jsonl"),
                    "ledger": str(_business_dir(simulation_id) / "ledger.jsonl"),
                    "state_snapshot": str(_business_dir(simulation_id) / "state_snapshot.json"),
                    "report_context": str(_business_dir(simulation_id) / "report_context.json"),
                }
            }
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Business simulation run failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/status", methods=["GET"])
def get_business_simulation_status(simulation_id: str):
    """Read common run_state.json for a business simulation."""
    try:
        run_state_path = _simulation_dir(simulation_id) / "run_state.json"
        if not run_state_path.exists():
            return jsonify({
                "success": False,
                "error": f"Run state not found for {simulation_id}"
            }), 404
        return jsonify({"success": True, "data": _read_json(run_state_path)})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@business_simulation_bp.route("/<simulation_id>/report-context", methods=["GET"])
def get_business_report_context(simulation_id: str):
    """Return report_context.json for the business report layer."""
    try:
        context_path = _business_dir(simulation_id) / "report_context.json"
        if not context_path.exists():
            return jsonify({
                "success": False,
                "error": f"Report context not found for {simulation_id}"
            }), 404
        return jsonify({"success": True, "data": _read_json(context_path)})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@business_simulation_bp.route("/<simulation_id>/scenario-revisions", methods=["GET"])
def get_business_scenario_revisions(simulation_id: str):
    """Return versioned scenario/fund-term change records."""
    try:
        revision_path = _revision_ledger_path(simulation_id)
        if not revision_path.exists():
            return jsonify({"success": True, "data": _empty_revision_ledger(simulation_id)})
        return jsonify({"success": True, "data": _read_json(revision_path)})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@business_simulation_bp.route("/<simulation_id>/financial-plan/commit", methods=["POST"])
def commit_proposed_financial_plan(simulation_id: str):
    """Commit proposed_financial_plan into the executable scenario.

    This is intentionally explicit because it changes future ledger outcomes.
    The route rewrites scenario/fund terms, then the caller should rerun the
    simulation to regenerate event logs, ledger, branch results, and reports.
    """
    try:
        business_dir = _business_dir(simulation_id)
        scenario_path = business_dir / "scenario.yaml"
        fund_terms_path = business_dir / "fund_terms.yaml"
        run_state_path = _simulation_dir(simulation_id) / "run_state.json"

        if not scenario_path.exists() or not fund_terms_path.exists():
            return jsonify({
                "success": False,
                "error": f"Business simulation inputs not found for {simulation_id}",
            }), 404

        scenario = load_structured_file(scenario_path)
        fund_terms = load_structured_file(fund_terms_path)
        proposed_financial_plan = scenario.get("proposed_financial_plan", {})
        if not proposed_financial_plan:
            return jsonify({"success": False, "error": "No proposed_financial_plan found"}), 400

        financial_plan = _financial_plan_from_proposal(
            proposed_financial_plan,
            (scenario.get("source_project") or {}).get("project_id"),
        )
        _sync_committed_financial_plan(fund_terms, scenario, financial_plan)
        scenario["proposed_financial_plan"]["status"] = "committed_to_financial_plan"
        scenario["proposed_financial_plan"]["committed_at"] = financial_plan["committed_at"]

        _write_yaml(fund_terms_path, fund_terms)
        _write_yaml(scenario_path, scenario)
        revision = _append_scenario_revision(
            simulation_id,
            change_type="financial_plan_commit",
            summary="Committed proposed_financial_plan into executable scenario and fund LP commitment.",
            changed_paths=[
                {"path": f"financial_plan.{key}", "after": financial_plan.get(key)}
                for key in [
                    "lp_commitment",
                    "capital_call_amount",
                    "investment_amount",
                    "liquidity_proceeds",
                    "distribution_amount",
                ]
            ],
            source={
                "proposal_source": proposed_financial_plan.get("source", ""),
                "commit_policy": proposed_financial_plan.get("commit_policy", ""),
                "committed_at": financial_plan.get("committed_at", ""),
            },
        )

        run_state = _read_json(run_state_path) if run_state_path.exists() else {}
        run_state.update({
            "simulation_id": simulation_id,
            "engine_type": "business_governance",
            "runner_status": "idle",
            "pending_change": "financial_plan_committed",
            "updated_at": datetime.utcnow().isoformat(),
        })
        write_json(run_state_path, run_state)

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "status": "financial_plan_committed",
                "rerun_required": True,
                "financial_plan": financial_plan,
                "revision": revision,
            }
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Business financial plan commit failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/fund-terms/commit", methods=["POST"])
def commit_proposed_fund_terms(simulation_id: str):
    """Commit proposed_fund_terms into executable fund_terms.yaml."""
    try:
        business_dir = _business_dir(simulation_id)
        scenario_path = business_dir / "scenario.yaml"
        fund_terms_path = business_dir / "fund_terms.yaml"
        run_state_path = _simulation_dir(simulation_id) / "run_state.json"

        if not scenario_path.exists() or not fund_terms_path.exists():
            return jsonify({
                "success": False,
                "error": f"Business simulation inputs not found for {simulation_id}",
            }), 404

        scenario = load_structured_file(scenario_path)
        fund_terms = load_structured_file(fund_terms_path)
        proposed_fund_terms = scenario.get("proposed_fund_terms", {})
        if not proposed_fund_terms:
            return jsonify({"success": False, "error": "No proposed_fund_terms found"}), 400

        committed_terms = _sync_committed_fund_terms(fund_terms, scenario, proposed_fund_terms)
        _write_yaml(fund_terms_path, fund_terms)
        _write_yaml(scenario_path, scenario)
        revision = _append_scenario_revision(
            simulation_id,
            change_type="fund_terms_commit",
            summary="Committed proposed_fund_terms into executable LPA clauses.",
            changed_paths=[
                {
                    "path": f"fund_terms.{key}",
                    "after": value.get("parameters", {}),
                }
                for key, value in committed_terms.get("committed", {}).items()
            ],
            source={
                "proposal_source": proposed_fund_terms.get("source", ""),
                "commit_policy": proposed_fund_terms.get("commit_policy", ""),
                "committed_at": committed_terms.get("committed_at", ""),
            },
        )

        run_state = _read_json(run_state_path) if run_state_path.exists() else {}
        run_state.update({
            "simulation_id": simulation_id,
            "engine_type": "business_governance",
            "runner_status": "idle",
            "pending_change": "fund_terms_committed",
            "updated_at": datetime.utcnow().isoformat(),
        })
        write_json(run_state_path, run_state)

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "status": "fund_terms_committed",
                "rerun_required": True,
                "fund_terms": committed_terms,
                "revision": revision,
            }
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Business fund terms commit failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/scenario-patch/preview", methods=["POST"])
def preview_business_scenario_patch(simulation_id: str):
    """Preview editable financial/fund-term changes without touching executable state."""
    try:
        business_dir = _business_dir(simulation_id)
        scenario_path = business_dir / "scenario.yaml"
        fund_terms_path = business_dir / "fund_terms.yaml"
        patch_path = business_dir / "scenario_patch.json"

        if not scenario_path.exists() or not fund_terms_path.exists():
            return jsonify({
                "success": False,
                "error": f"Business simulation inputs not found for {simulation_id}",
            }), 404

        patch = _normalize_scenario_patch(request.get_json(silent=True) or {})
        scenario = load_structured_file(scenario_path)
        fund_terms = load_structured_file(fund_terms_path)
        preview = _build_scenario_patch_preview(simulation_id, fund_terms, scenario, patch)
        write_json(patch_path, preview)
        return jsonify({"success": True, "data": preview})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Business scenario patch preview failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/scenario-patch/commit", methods=["POST"])
def commit_business_scenario_patch(simulation_id: str):
    """Commit editable financial/fund-term patch into scenario.yaml and fund_terms.yaml."""
    try:
        business_dir = _business_dir(simulation_id)
        scenario_path = business_dir / "scenario.yaml"
        fund_terms_path = business_dir / "fund_terms.yaml"
        patch_path = business_dir / "scenario_patch.json"
        run_state_path = _simulation_dir(simulation_id) / "run_state.json"

        if not scenario_path.exists() or not fund_terms_path.exists():
            return jsonify({
                "success": False,
                "error": f"Business simulation inputs not found for {simulation_id}",
            }), 404

        patch = _normalize_scenario_patch(request.get_json(silent=True) or {})
        scenario = load_structured_file(scenario_path)
        fund_terms = load_structured_file(fund_terms_path)
        committed = _apply_scenario_patch(simulation_id, fund_terms, scenario, patch)

        _write_yaml(fund_terms_path, fund_terms)
        _write_yaml(scenario_path, scenario)
        write_json(patch_path, committed)
        revision = _append_scenario_revision(
            simulation_id,
            change_type="manual_scenario_patch_commit",
            summary="Committed manual editable workspace patch into scenario and fund terms.",
            changed_paths=committed.get("changed_paths", []),
            source={
                "patch_type": committed.get("patch_type", ""),
                "commit_policy": committed.get("commit_policy", ""),
                "scenario_patch_file": "scenario_patch.json",
            },
        )
        committed["revision"] = revision
        write_json(patch_path, committed)

        run_state = _read_json(run_state_path) if run_state_path.exists() else {}
        run_state.update({
            "simulation_id": simulation_id,
            "engine_type": "business_governance",
            "runner_status": "idle",
            "pending_change": "scenario_patch_committed",
            "updated_at": datetime.utcnow().isoformat(),
        })
        write_json(run_state_path, run_state)

        return jsonify({"success": True, "data": committed})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Business scenario patch commit failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


def _build_markdown_report(context: dict) -> str:
    title = context.get("title", "Business Governance Simulation Report")
    scenario = context.get("scenario_summary", {})
    cashflow = context.get("cashflow_summary", {})
    governance = context.get("governance_summary", {})
    reserve = context.get("reserve_summary", {})
    audit = context.get("audit_summary", {})
    findings = context.get("executive_findings", [])
    timeline = context.get("timeline", [])
    branches = context.get("branch_summaries", [])
    branch_risk_summary = context.get("branch_risk_summary", [])
    portfolio_scenario_expansion = context.get("portfolio_scenario_expansion", {})
    source_project = context.get("source_project", {})
    object_name_map = context.get("object_name_map", {})
    event_plan = context.get("event_plan_summary", {})
    financial_plan = context.get("financial_plan", {})
    proposed_financial_plan = context.get("proposed_financial_plan", {})
    proposed_fund_terms = context.get("proposed_fund_terms", {})
    fund_terms_summary = context.get("fund_terms_summary", {})
    manual_scenario_patch = context.get("manual_scenario_patch", {})
    scenario_revision = context.get("scenario_revision", {})
    lifecycle = context.get("fund_lifecycle_summary", {})
    capital_call_schedule = context.get("capital_call_schedule", [])
    nav_snapshots = context.get("nav_snapshots", [])
    lp_readiness = context.get("lp_readiness_summary", {})
    evidence_bindings = context.get("evidence_bindings", {})
    evidence_items = evidence_bindings.get("bindings", [])
    financial_hints = source_project.get("financial_hints", {})
    fund_term_hints = source_project.get("fund_term_hints", {})

    lines = [
        f"# {title}",
        "",
        "## Executive Findings",
        "",
    ]
    lines.extend(f"- {finding}" for finding in findings)
    lines.extend([
        "",
        "## Scenario",
        "",
        f"- Scenario ID: `{scenario.get('scenario_id', '')}`",
        f"- Branch ID: `{scenario.get('branch_id', '')}`",
        f"- Branches: {', '.join(scenario.get('branches', []))}",
        "",
        "## Source Project",
        "",
        f"- Project ID: `{source_project.get('project_id', '')}`",
        f"- Graph ID: `{source_project.get('graph_id', '')}`",
        f"- Requirement: {source_project.get('simulation_requirement', '')}",
        f"- Ontology entity types: {', '.join(source_project.get('ontology_entity_types', []))}",
        "",
        "## Object Map",
        "",
    ])
    for object_id, name in object_name_map.items():
        lines.append(f"- `{object_id}`: {name}")

    lines.extend([
        "",
        "## Event Plan",
        "",
        f"- Source: `{event_plan.get('source', '')}`",
        f"- Strategy: `{event_plan.get('strategy', '')}`",
        f"- Planned events: {event_plan.get('planned_events_count', 0)}",
        f"- Planned event types: {', '.join(event_plan.get('planned_event_types', []))}",
        "",
        "## Branch Risk Summary",
        "",
    ])
    for item in branch_risk_summary:
        lines.append(
            f"- `{item.get('branch_id')}`: {item.get('risk_level')} "
            f"({item.get('risk_score', 0)}) - {item.get('primary_action', '')}"
        )

    lines.extend([
        "",
        "## Portfolio Scenario Expansion",
        "",
        f"- Milestone: `{portfolio_scenario_expansion.get('milestone', '')}`",
        f"- Generation policy: `{portfolio_scenario_expansion.get('generation_policy', '')}`",
        f"- Branch count: {portfolio_scenario_expansion.get('branch_count', len(branches))}",
        f"- Coverage: {', '.join(portfolio_scenario_expansion.get('coverage', []))}",
        "",
    ])

    lines.extend([
        "",
        "## Fund Terms",
        "",
        f"- LP commitment: {fund_terms_summary.get('lp_commitment', 0):,.2f}",
        f"- Management fee: `{fund_terms_summary.get('management_fee', {})}`",
        f"- Voting threshold: `{fund_terms_summary.get('voting_threshold', {})}`",
        f"- Waterfall rule: `{fund_terms_summary.get('waterfall_rule', {})}`",
        "",
        "## Manual Scenario Patch",
        "",
        f"- Status: `{manual_scenario_patch.get('status', 'none')}`",
        f"- Commit policy: `{manual_scenario_patch.get('commit_policy', 'manual_patch_requires_explicit_commit_before_rerun')}`",
        f"- Changed paths: {len(manual_scenario_patch.get('changed_paths', []))}",
        f"- Impact preview: `{manual_scenario_patch.get('impact_preview', {})}`",
        "",
        "## Scenario Revision",
        "",
        f"- Current revision: `{scenario_revision.get('current_revision_id', '')}`",
        f"- Revisions count: {scenario_revision.get('revisions_count', 0)}",
        f"- Latest change type: `{(scenario_revision.get('latest_revision') or {}).get('change_type', '')}`",
        f"- Latest summary: {(scenario_revision.get('latest_revision') or {}).get('summary', '')}",
        "",
        "## Proposed Fund Terms",
        "",
        f"- Source: `{proposed_fund_terms.get('source', '')}`",
        f"- Status: `{proposed_fund_terms.get('status', 'not_committed_to_rules')}`",
        f"- Commit policy: `{proposed_fund_terms.get('commit_policy', 'proposal_only_requires_user_confirmation')}`",
        f"- Candidate sentences: {len((proposed_fund_terms.get('hints') or {}).get('sentences', []))}",
        "",
    ])
    for key, proposal in proposed_fund_terms.get("proposals", {}).items():
        lines.append(
            f"- {key}: `{proposal.get('clause_type', '')}` "
            f"{proposal.get('parameters', {})} "
            f"(confidence: {proposal.get('confidence', 'unknown')})"
        )

    lines.extend([
        "",
        "## Financial Plan",
        "",
        f"- Source: `{financial_plan.get('source', '')}`",
        f"- LP commitment: {financial_plan.get('lp_commitment', 0):,.2f}",
        f"- Capital call amount: {financial_plan.get('capital_call_amount', 0):,.2f}",
        f"- Investment amount: {financial_plan.get('investment_amount', 0):,.2f}",
        f"- Liquidity proceeds: {financial_plan.get('liquidity_proceeds', 0):,.2f}",
        f"- Distribution amount: {financial_plan.get('distribution_amount', 0):,.2f}",
        f"- Follow-on reserve amount: {financial_plan.get('follow_on_reserve_amount', 0):,.2f}",
        "",
        "## Fund Lifecycle Summary",
        "",
        f"- Focus: `{lifecycle.get('focus', '')}`",
        f"- Capital call rounds: {lifecycle.get('capital_call_rounds', 0)}",
        f"- Unfunded commitment: {(lifecycle.get('commitment_summary') or {}).get('unfunded_commitment', 0):,.2f}",
        f"- Net asset value: {(lifecycle.get('nav_summary') or {}).get('net_asset_value', 0):,.2f}",
        f"- Paid-in multiple: {(lifecycle.get('nav_summary') or {}).get('paid_in_multiple', 0)}",
        f"- Follow-on reserve status: `{(lifecycle.get('follow_on_reserve') or {}).get('status', '')}`",
        f"- Follow-on reserve gap: {(lifecycle.get('follow_on_reserve') or {}).get('gap', 0):,.2f}",
        "",
        "## LP Readiness",
        "",
        f"- Status: `{lp_readiness.get('status', '')}`",
        f"- Recommended next step: {lp_readiness.get('recommended_next_step', '')}",
        "",
    ])
    for item in lp_readiness.get("items", []):
        lines.append(
            f"- {item.get('item', '')}: `{item.get('status', '')}` "
            f"(owner: {item.get('owner', '')})"
        )

    lines.extend([
        "",
        "## Capital Call Schedule",
        "",
    ])
    for call in capital_call_schedule:
        lines.append(
            f"- Round {call.get('round')}: `{call.get('type')}` "
            f"{call.get('amount', 0):,.2f} due {call.get('due_date', '')} "
            f"status `{call.get('status', '')}` purpose `{call.get('purpose', '')}`"
        )

    lines.extend([
        "",
        "## NAV Snapshots",
        "",
    ])
    for snapshot in nav_snapshots:
        lines.append(
            f"- {snapshot.get('simulation_time')}: {snapshot.get('label', '')} - "
            f"NAV {snapshot.get('net_asset_value', 0):,.2f}, "
            f"cash {snapshot.get('cash', 0):,.2f}, portfolio {snapshot.get('portfolio_nav', 0):,.2f}"
        )

    lines.extend([
        "",
        "## Evidence Bindings",
        "",
        f"- Binding policy: `{evidence_bindings.get('binding_policy', 'evidence_only_does_not_mutate_ledger')}`",
        f"- Bindings count: {evidence_bindings.get('bindings_count', len(evidence_items))}",
        "",
    ])
    for item in evidence_items[:12]:
        lines.append(
            f"- `{item.get('target_path', '')}` ({item.get('target_type', '')}, "
            f"confidence `{item.get('confidence', '')}`): {item.get('source_snippet', '')} "
            f"[{item.get('source_ref', '')}]"
        )

    lines.extend([
        "",
        "## Proposed Financial Plan",
        "",
        f"- Source: `{proposed_financial_plan.get('source', '')}`",
        f"- Status: `{proposed_financial_plan.get('status', 'not_committed_to_ledger')}`",
        f"- Commit policy: `{proposed_financial_plan.get('commit_policy', 'proposal_only_requires_user_confirmation')}`",
        f"- Parsed amount candidates: {len(proposed_financial_plan.get('parsed_amounts', []))}",
        "",
    ])
    for key, proposal in proposed_financial_plan.get("proposals", {}).items():
        lines.append(
            f"- {key}: {proposal.get('value', 0):,.2f} "
            f"(confidence: {proposal.get('confidence', 'unknown')})"
        )

    lines.extend([
        "",
        "## Financial Hints",
        "",
        f"- Source: `{financial_hints.get('source', '')}`",
        f"- Commit policy: `{financial_hints.get('commit_policy', 'hints_only')}`",
        f"- Amount candidates: {', '.join(financial_hints.get('amounts', []))}",
        f"- Percentage candidates: {', '.join(financial_hints.get('percentages', []))}",
        "",
        "## Fund Term Hints",
        "",
        f"- Source: `{fund_term_hints.get('source', '')}`",
        f"- Commit policy: `{fund_term_hints.get('commit_policy', 'hints_only')}`",
        f"- Percentage candidates: {', '.join(fund_term_hints.get('percentages', []))}",
        f"- Day candidates: {', '.join(fund_term_hints.get('days', []))}",
        "",
        "## Cashflow Summary",
        "",
        f"- Capital called: {cashflow.get('capital_called', 0):,.2f}",
        f"- Capital paid: {cashflow.get('capital_paid', 0):,.2f}",
        f"- Distributions: {cashflow.get('distributions', 0):,.2f}",
        f"- Fees: {cashflow.get('fees', 0):,.2f}",
        f"- Penalties: {cashflow.get('penalties', 0):,.2f}",
        "",
        "## Governance Summary",
        "",
        f"- Decisions: {governance.get('decisions', 0)}",
        f"- Approvals: {governance.get('approvals', 0)}",
        f"- Rejections: {governance.get('rejections', 0)}",
        f"- Vetoes: {governance.get('vetoes', 0)}",
        f"- Reserve compliant: {governance.get('reserve_compliant')}",
        f"- Waterfall applied: {governance.get('waterfall_applied')}",
        f"- Audit exceptions: {governance.get('audit_exceptions', 0)}",
        "",
        "## Reserve Summary",
        "",
        f"- Required reserve: {reserve.get('required', 0):,.2f}",
        f"- Projected reserve after distribution: {reserve.get('projected_after_distribution', 0):,.2f}",
        f"- Reserve shortfall: {reserve.get('shortfall', 0):,.2f}",
        f"- Compliant: {reserve.get('compliant')}",
        "",
        "## Audit Summary",
        "",
        f"- Exceptions count: {audit.get('exceptions_count', 0)}",
        "",
        "## Timeline",
        "",
    ])
    for exception in audit.get("exceptions", []):
        lines.append(f"- {exception.get('severity', 'unknown')}: {exception.get('message', '')}")
    if audit.get("exceptions"):
        lines.append("")

    for item in timeline:
        lines.append(
            f"- {item.get('simulation_time')}: **{item.get('event_type')}** - {item.get('summary')}"
        )

    lines.extend(["", "## Branch Notes", ""])
    for branch in branches:
        lines.append(
            f"- `{branch.get('branch_id')}` ({branch.get('status')}, "
            f"{branch.get('risk_level', 'unknown')} {branch.get('risk_score', 0)}): "
            f"{branch.get('summary')} Primary action: {branch.get('primary_action', '')}"
        )

    lines.extend([
        "",
        "## Audit Trail",
        "",
        "This report is generated from `report_context.json`, which is derived from the business event log, ledger, decision records, rule execution records, and final state snapshot.",
        "",
    ])
    return "\n".join(lines)


def _build_governance_packet(context: dict) -> dict:
    simulation_id = context.get("simulation_id", "")
    title = context.get("title", "Business Governance Simulation")
    reserve = context.get("reserve_summary", {})
    audit = context.get("audit_summary", {})
    cashflow = context.get("cashflow_summary", {})
    governance = context.get("governance_summary", {})
    branch_risk_summary = context.get("branch_risk_summary", [])
    branch_results = context.get("branch_results", {}).get("branches", {})
    fund_terms = context.get("fund_terms_summary", {})
    source_project = context.get("source_project", {})
    scenario_revision = context.get("scenario_revision", {})
    evidence_bindings = context.get("evidence_bindings", {})
    evidence_items = evidence_bindings.get("bindings", [])
    key_binding_types = {
        "lp_capital_lifecycle": 0,
        "lp_capital_strategy": 1,
        "capital_call": 2,
        "nav_snapshot": 3,
        "branch_risk": 4,
        "financial_plan_proposal": 5,
        "fund_term_proposal": 6,
    }
    key_evidence_bindings = [
        item for item in sorted(
            evidence_items,
            key=lambda value: key_binding_types.get(value.get("target_type"), 99),
        )
        if item.get("target_type") in key_binding_types
    ][:16]
    highest_risk = branch_risk_summary[0] if branch_risk_summary else {}

    action_required = (
        highest_risk.get("risk_level") in {"critical", "high"}
        or reserve.get("compliant") is False
        or int(audit.get("exceptions_count", 0) or 0) > 0
    )
    decision_status = "action_required" if action_required else "review_ready"
    recommendation = (
        "Hold distribution or obtain LPAC reserve waiver before execution."
        if reserve.get("compliant") is False
        else "Proceed with governance approvals and archive the audit-ready evidence packet."
    )

    required_decisions: list[dict] = []
    if reserve.get("compliant") is False:
        required_decisions.append({
            "decision_id": "reserve_shortfall_resolution",
            "owner": "LPAC",
            "decision": "Approve reserve waiver, reduce distribution, or call additional capital.",
            "severity": "high",
            "reason": f"Projected reserve shortfall is {float(reserve.get('shortfall', 0) or 0):,.2f}.",
            "due_timing": "before_distribution",
            "evidence_refs": ["report_context.json#reserve_summary", "branch_results.json#risk_summary"],
        })
    if highest_risk.get("risk_level") in {"critical", "high"}:
        required_decisions.append({
            "decision_id": "highest_risk_branch_response",
            "owner": "GP",
            "decision": highest_risk.get("primary_action", "Review highest-risk branch."),
            "severity": highest_risk.get("risk_level", "medium"),
            "reason": f"Highest-risk branch is {highest_risk.get('branch_id')} with score {highest_risk.get('risk_score')}.",
            "due_timing": "next_governance_meeting",
            "evidence_refs": [f"branch_results.json#branches.{highest_risk.get('branch_id', '')}"],
        })
    if int(audit.get("exceptions_count", 0) or 0) > 0:
        required_decisions.append({
            "decision_id": "audit_exception_remediation",
            "owner": "Auditor",
            "decision": "Resolve audit exceptions before final report circulation.",
            "severity": "high",
            "reason": f"Audit exceptions count is {audit.get('exceptions_count', 0)}.",
            "due_timing": "before_report_release",
            "evidence_refs": ["report_context.json#audit_summary"],
        })
    if not required_decisions:
        required_decisions.append({
            "decision_id": "standard_distribution_review",
            "owner": "GP",
            "decision": "Confirm distribution notice, waterfall calculation, and audit archive.",
            "severity": "low",
            "reason": "No reserve shortfall or audit exception was detected.",
            "due_timing": "before_distribution_notice",
            "evidence_refs": ["ledger.jsonl", "rule_execution_records.jsonl", "business_report.md"],
        })

    branch_actions = []
    for branch_id, branch in branch_results.items():
        profile = branch.get("governance") or {}
        branch_actions.append({
            "branch_id": branch_id,
            "risk_level": profile.get("risk_level", "unknown"),
            "risk_score": profile.get("risk_score", 0),
            "triggered_terms": profile.get("triggered_terms", []),
            "governance_actions": profile.get("governance_actions", []),
            "audit_flags": profile.get("audit_flags", []),
            "summary": branch.get("summary", ""),
        })

    return {
        "schema_version": "0.1",
        "packet_type": "governance_decision_packet",
        "simulation_id": simulation_id,
        "title": title,
        "generated_at": datetime.utcnow().isoformat(),
        "decision_status": decision_status,
        "decision_subject": "LPAC / IC review of fund governance simulation outcomes",
        "recommendation": recommendation,
        "participants": ["GP", "Investment Committee", "LPAC", "Auditor"],
        "source_project": {
            "project_id": source_project.get("project_id", ""),
            "graph_id": source_project.get("graph_id", ""),
            "project_name": source_project.get("project_name", ""),
        },
        "scenario_revision": {
            "current_revision_id": scenario_revision.get("current_revision_id", ""),
            "revisions_count": scenario_revision.get("revisions_count", 0),
            "latest_change_type": (scenario_revision.get("latest_revision") or {}).get("change_type", ""),
            "latest_summary": (scenario_revision.get("latest_revision") or {}).get("summary", ""),
        },
        "key_metrics": {
            "capital_called": cashflow.get("capital_called", 0),
            "capital_paid": cashflow.get("capital_paid", 0),
            "distributions": cashflow.get("distributions", 0),
            "fees": cashflow.get("fees", 0),
            "reserve_required": reserve.get("required", 0),
            "reserve_shortfall": reserve.get("shortfall", 0),
            "reserve_compliant": reserve.get("compliant"),
            "audit_exceptions": audit.get("exceptions_count", 0),
            "waterfall_applied": governance.get("waterfall_applied"),
        },
        "fund_terms_snapshot": {
            "management_fee": fund_terms.get("management_fee", {}),
            "voting_threshold": fund_terms.get("voting_threshold", {}),
            "waterfall_rule": fund_terms.get("waterfall_rule", {}),
            "reserve_account": fund_terms.get("reserve_account", {}),
            "default_remedies": fund_terms.get("default_remedies", {}),
            "audit_review": fund_terms.get("audit_review", {}),
        },
        "highest_risk_branch": highest_risk,
        "required_decisions": required_decisions,
        "branch_risk_summary": branch_risk_summary,
        "branch_actions": branch_actions,
        "evidence_bindings": {
            "bindings_count": evidence_bindings.get("bindings_count", len(evidence_items)),
            "binding_policy": evidence_bindings.get("binding_policy", "evidence_only_does_not_mutate_ledger"),
            "key_bindings": key_evidence_bindings,
            "audit_trail": evidence_bindings.get("audit_trail", []),
        },
        "evidence_index": [
            {"file": "event_log.jsonl", "purpose": "Object-centric event replay"},
            {"file": "ledger.jsonl", "purpose": "Double-entry cashflow evidence"},
            {"file": "decision_records.jsonl", "purpose": "IC/approval evidence"},
            {"file": "rule_execution_records.jsonl", "purpose": "Deterministic rule checks"},
            {"file": "branch_results.json", "purpose": "Scenario branch risk comparison"},
            {"file": "report_context.json", "purpose": "Report-ready summarized context"},
            {"file": "scenario_patch.json", "purpose": "Editable scenario/fund-term patch preview and commit evidence"},
            {"file": "scenario_revisions.json", "purpose": "Versioned governance input change ledger"},
            {"file": "evidence_bindings.json", "purpose": "Source snippets, confidence, and target-path evidence bindings"},
            {"file": "governance_remediation_plan.json", "purpose": "Revision-bound remediation options for required decisions"},
            {"file": "business_report.md", "purpose": "Human-readable governance report"},
        ],
    }


def _build_governance_memo(packet: dict) -> str:
    lines = [
        f"# {packet.get('title', 'Governance Decision Packet')}",
        "",
        "## Decision Packet",
        "",
        f"- Packet type: `{packet.get('packet_type', '')}`",
        f"- Simulation ID: `{packet.get('simulation_id', '')}`",
        f"- Decision status: `{packet.get('decision_status', '')}`",
        f"- Subject: {packet.get('decision_subject', '')}",
        f"- Recommendation: {packet.get('recommendation', '')}",
        "",
        "## Key Metrics",
        "",
    ]
    for key, value in packet.get("key_metrics", {}).items():
        lines.append(f"- {key}: `{value}`")

    scenario_revision = packet.get("scenario_revision", {})
    lines.extend([
        "",
        "## Scenario Revision",
        "",
        f"- Packet revision: `{scenario_revision.get('current_revision_id', '')}`",
        f"- Revisions count: `{scenario_revision.get('revisions_count', 0)}`",
        f"- Latest change: `{scenario_revision.get('latest_change_type', '')}`",
        f"- Latest summary: {scenario_revision.get('latest_summary', '')}",
    ])

    highest = packet.get("highest_risk_branch", {})
    lines.extend([
        "",
        "## Highest Risk Branch",
        "",
        f"- Branch: `{highest.get('branch_id', '')}`",
        f"- Risk: `{highest.get('risk_level', '')}` / `{highest.get('risk_score', 0)}`",
        f"- Primary action: {highest.get('primary_action', '')}",
        "",
        "## Required Decisions",
        "",
    ])
    for item in packet.get("required_decisions", []):
        lines.append(
            f"- `{item.get('decision_id')}` ({item.get('owner')}, {item.get('severity')}): "
            f"{item.get('decision')} Reason: {item.get('reason')}"
        )

    lines.extend(["", "## Branch Action Plan", ""])
    for item in packet.get("branch_actions", []):
        actions = "; ".join(item.get("governance_actions", []))
        terms = ", ".join(item.get("triggered_terms", []))
        lines.append(
            f"- `{item.get('branch_id')}` {item.get('risk_level')} {item.get('risk_score')}: "
            f"{actions} Triggered terms: {terms}"
        )

    lines.extend(["", "## Evidence Index", ""])
    for item in packet.get("evidence_index", []):
        lines.append(f"- `{item.get('file')}`: {item.get('purpose')}")

    lines.append("")
    return "\n".join(lines)


def _money(value) -> str:
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _table_text(value) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _string_list(values: list) -> list[str]:
    formatted: list[str] = []
    for value in values or []:
        if isinstance(value, dict):
            formatted.append(
                value.get("term")
                or value.get("message")
                or value.get("rule_id")
                or value.get("severity")
                or json.dumps(value, ensure_ascii=False, sort_keys=True)
            )
        else:
            formatted.append(str(value))
    return formatted


def _markdown_table(headers: list[str], rows: list[list]) -> list[str]:
    if not rows:
        return ["_No items._"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_table_text(item) for item in row) + " |")
    return lines


def _dedupe_evidence_items(items: list[dict], limit: int = 24) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for item in items:
        key = (item.get("target_path", ""), item.get("source_ref", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _build_meeting_pack(simulation_id: str, context: dict, packet: dict, review: dict, evidence_bindings: dict) -> dict:
    lifecycle = context.get("fund_lifecycle_summary", {})
    commitment = lifecycle.get("commitment_summary") or {}
    nav = lifecycle.get("nav_summary") or {}
    reserve = context.get("reserve_summary", {})
    cashflow = context.get("cashflow_summary", {})
    financial_plan = context.get("financial_plan", {})
    lp_readiness = context.get("lp_readiness_summary", {})
    proposed_financial = context.get("proposed_financial_plan", {})
    proposed_terms = context.get("proposed_fund_terms", {})
    scenario_expansion = context.get("portfolio_scenario_expansion", {})
    key_bindings = (packet.get("evidence_bindings") or {}).get("key_bindings", [])
    all_bindings = evidence_bindings.get("bindings", [])
    evidence_appendix = _dedupe_evidence_items(key_bindings + all_bindings, limit=28)

    decision_rows = []
    for item in packet.get("required_decisions", []):
        decision_rows.append({
            "decision_id": item.get("decision_id", ""),
            "owner": item.get("owner", ""),
            "severity": item.get("severity", ""),
            "decision": item.get("decision", ""),
            "due_timing": item.get("due_timing", ""),
            "evidence_refs": item.get("evidence_refs", []),
        })

    risk_rows = []
    branch_actions_by_id = {
        item.get("branch_id"): item
        for item in packet.get("branch_actions", [])
        if item.get("branch_id")
    }
    for item in packet.get("branch_risk_summary", []):
        branch_id = item.get("branch_id", "")
        action = branch_actions_by_id.get(branch_id, {})
        risk_rows.append({
            "branch_id": branch_id,
            "risk_level": item.get("risk_level", ""),
            "risk_score": item.get("risk_score", 0),
            "primary_action": item.get("primary_action", ""),
            "triggered_terms": _string_list(action.get("triggered_terms", [])),
            "audit_flags": _string_list(action.get("audit_flags", [])),
        })

    source_files = packet.get("evidence_index", []) + [
        {"file": "meeting_pack.json", "purpose": "Structured LPAC / IC meeting pack export"},
        {"file": "meeting_pack.md", "purpose": "Markdown meeting pack for review and GitHub sharing"},
        {"file": "meeting_pack.docx", "purpose": "Editable meeting pack document"},
        {"file": "meeting_pack.pdf", "purpose": "Portable meeting pack snapshot"},
    ]

    return {
        "schema_version": "0.1",
        "pack_type": "lpac_ic_meeting_pack",
        "simulation_id": simulation_id,
        "title": f"{context.get('title', 'Business Governance Simulation')} LPAC / IC Meeting Pack",
        "generated_at": datetime.utcnow().isoformat(),
        "generation_policy": "export_only_does_not_mutate_ledger_or_review_state",
        "meeting": {
            "audience": ["LP", "LPAC", "Investment Committee", "GP", "Auditor"],
            "purpose": "Prepare LP-facing capital, governance, risk, and evidence review materials from the latest simulation outputs.",
            "agenda": [
                "Confirm LP capital entry status, unfunded commitment, and wiring/readiness items.",
                "Review capital calls, follow-on reserve, NAV, and distribution posture.",
                "Review required LPAC / IC decisions and owner timing.",
                "Review highest-risk branches and mitigation options.",
                "Review evidence bindings and document source confidence.",
                "Confirm next operating actions before LP circulation or rerun.",
            ],
        },
        "lp_capital_brief": {
            "capital_called": cashflow.get("capital_called", 0),
            "capital_paid": cashflow.get("capital_paid", 0),
            "unfunded_commitment": commitment.get("unfunded_commitment", cashflow.get("unfunded_commitment", 0)),
            "capital_call_rounds": lifecycle.get("capital_call_rounds", len(context.get("capital_call_schedule", []))),
            "net_asset_value": nav.get("net_asset_value", cashflow.get("net_asset_value", 0)),
            "paid_in_multiple": nav.get("paid_in_multiple", 0),
            "follow_on_reserve_status": (lifecycle.get("follow_on_reserve") or {}).get("status", ""),
            "follow_on_reserve_gap": (lifecycle.get("follow_on_reserve") or {}).get("gap", 0),
            "reserve_required": reserve.get("required", 0),
            "reserve_shortfall": reserve.get("shortfall", 0),
            "lp_readiness_status": lp_readiness.get("status", ""),
            "lp_readiness_next_step": lp_readiness.get("recommended_next_step", ""),
            "capital_call_schedule": context.get("capital_call_schedule", []),
            "lp_readiness_items": lp_readiness.get("items", []),
        },
        "strategy_readiness": {
            "financial_plan_source": financial_plan.get("source", ""),
            "proposed_financial_status": proposed_financial.get("status", "not_committed_to_ledger"),
            "proposed_financial_commit_policy": proposed_financial.get("commit_policy", "proposal_only_requires_user_confirmation"),
            "proposed_terms_status": proposed_terms.get("status", "not_committed_to_rules"),
            "proposed_terms_commit_policy": proposed_terms.get("commit_policy", "proposal_only_requires_user_confirmation"),
        },
        "scenario_expansion": scenario_expansion,
        "packet_status": {
            "decision_status": packet.get("decision_status", ""),
            "review_status": review.get("effective_review_status") or review.get("review_status", ""),
            "packet_revision_id": review.get("packet_revision_id", ""),
            "current_revision_id": review.get("current_revision_id", ""),
            "packet_is_stale": review.get("packet_is_stale", False),
            "recommendation": packet.get("recommendation", ""),
        },
        "decision_table": decision_rows,
        "risk_appendix": risk_rows,
        "evidence_appendix": evidence_appendix,
        "source_files": source_files,
    }


def _build_meeting_pack_markdown(pack: dict) -> str:
    capital = pack.get("lp_capital_brief", {})
    status = pack.get("packet_status", {})
    strategy = pack.get("strategy_readiness", {})
    scenario_expansion = pack.get("scenario_expansion", {})
    lines = [
        f"# {pack.get('title', 'LPAC / IC Meeting Pack')}",
        "",
        "## Meeting Agenda",
        "",
    ]
    lines.extend(f"- {item}" for item in (pack.get("meeting") or {}).get("agenda", []))
    lines.extend([
        "",
        "## LP Capital Brief",
        "",
        f"- Capital called: {_money(capital.get('capital_called'))}",
        f"- Capital paid: {_money(capital.get('capital_paid'))}",
        f"- Unfunded commitment: {_money(capital.get('unfunded_commitment'))}",
        f"- Capital call rounds: {capital.get('capital_call_rounds', 0)}",
        f"- NAV: {_money(capital.get('net_asset_value'))}",
        f"- Paid-in multiple: {capital.get('paid_in_multiple', 0)}",
        f"- Follow-on reserve status: `{capital.get('follow_on_reserve_status', '')}`",
        f"- Follow-on reserve gap: {_money(capital.get('follow_on_reserve_gap'))}",
        f"- Reserve required: {_money(capital.get('reserve_required'))}",
        f"- Reserve shortfall: {_money(capital.get('reserve_shortfall'))}",
        f"- LP readiness: `{capital.get('lp_readiness_status', '')}`",
        f"- Recommended LP next step: {capital.get('lp_readiness_next_step', '')}",
        "",
        "## Capital Call Schedule",
        "",
    ])
    for item in capital.get("capital_call_schedule", []):
        lines.append(
            f"- Round {item.get('round')}: `{item.get('type')}` {_money(item.get('amount'))} "
            f"due {item.get('due_date', '')}; status `{item.get('status', '')}`; purpose {item.get('purpose', '')}"
        )
    lines.extend(["", "## LP Readiness Items", ""])
    for item in capital.get("lp_readiness_items", []):
        lines.append(f"- {item.get('item', '')}: `{item.get('status', '')}` (owner: {item.get('owner', '')})")

    lines.extend([
        "",
        "## Packet Status",
        "",
        f"- Decision status: `{status.get('decision_status', '')}`",
        f"- Review status: `{status.get('review_status', '')}`",
        f"- Packet revision: `{status.get('packet_revision_id', '')}`",
        f"- Current revision: `{status.get('current_revision_id', '')}`",
        f"- Packet stale: `{status.get('packet_is_stale', False)}`",
        f"- Recommendation: {status.get('recommendation', '')}",
        "",
        "## Strategy Readiness",
        "",
        f"- Financial plan source: `{strategy.get('financial_plan_source', '')}`",
        f"- Proposed financial status: `{strategy.get('proposed_financial_status', '')}`",
        f"- Proposed financial commit policy: `{strategy.get('proposed_financial_commit_policy', '')}`",
        f"- Proposed terms status: `{strategy.get('proposed_terms_status', '')}`",
        f"- Proposed terms commit policy: `{strategy.get('proposed_terms_commit_policy', '')}`",
        "",
        "## Portfolio Scenario Expansion",
        "",
        f"- Milestone: `{scenario_expansion.get('milestone', '')}`",
        f"- Generation policy: `{scenario_expansion.get('generation_policy', '')}`",
        f"- Branch count: {scenario_expansion.get('branch_count', 0)}",
        f"- Coverage: {', '.join(scenario_expansion.get('coverage', []))}",
        "",
        "## Decision Table",
        "",
    ])
    lines.extend(_markdown_table(
        ["Decision ID", "Owner", "Severity", "Due", "Decision", "Evidence"],
        [
            [
                item.get("decision_id", ""),
                item.get("owner", ""),
                item.get("severity", ""),
                item.get("due_timing", ""),
                item.get("decision", ""),
                ", ".join(item.get("evidence_refs", [])),
            ]
            for item in pack.get("decision_table", [])
        ],
    ))
    lines.extend(["", "## Risk Appendix", ""])
    lines.extend(_markdown_table(
        ["Branch", "Risk", "Score", "Primary Action", "Triggered Terms", "Audit Flags"],
        [
            [
                item.get("branch_id", ""),
                item.get("risk_level", ""),
                item.get("risk_score", 0),
                item.get("primary_action", ""),
                ", ".join(item.get("triggered_terms", [])),
                ", ".join(item.get("audit_flags", [])),
            ]
            for item in pack.get("risk_appendix", [])
        ],
    ))
    lines.extend(["", "## Evidence Appendix", ""])
    lines.extend(_markdown_table(
        ["Target", "Type", "Confidence", "Source", "Snippet"],
        [
            [
                item.get("target_path", ""),
                item.get("target_type", ""),
                item.get("confidence", ""),
                item.get("source_ref", ""),
                item.get("source_snippet", ""),
            ]
            for item in pack.get("evidence_appendix", [])
        ],
    ))
    lines.extend(["", "## Source Files", ""])
    for item in pack.get("source_files", []):
        lines.append(f"- `{item.get('file', '')}`: {item.get('purpose', '')}")
    lines.extend([
        "",
        "## Audit Note",
        "",
        f"- Generation policy: `{pack.get('generation_policy', '')}`",
        "- Meeting pack generation packages current simulation evidence only; it does not approve, waive, rerun, or mutate authoritative ledger state.",
        "",
    ])
    return "\n".join(lines)


def _docx_paragraph(text: str, style: str | None = None, bold: bool = False) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    escaped = html.escape(text, quote=False)
    if bold:
        run = f"<w:r><w:rPr><w:b/></w:rPr><w:t>{escaped}</w:t></w:r>"
    else:
        run = f"<w:r><w:t>{escaped}</w:t></w:r>"
    return f"<w:p>{style_xml}{run}</w:p>"


def _write_docx_pack(path: Path, markdown: str) -> None:
    paragraphs: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            paragraphs.append("<w:p/>")
        elif line.startswith("# "):
            paragraphs.append(_docx_paragraph(line[2:], style="Title", bold=True))
        elif line.startswith("## "):
            paragraphs.append(_docx_paragraph(line[3:], style="Heading1", bold=True))
        elif line.startswith("- "):
            paragraphs.append(_docx_paragraph("• " + line[2:]))
        else:
            paragraphs.append(_docx_paragraph(line))
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)


def _pdf_escape(text: str) -> str:
    latin = text.encode("latin-1", errors="replace").decode("latin-1")
    return latin.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _markdown_to_pdf_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            line = line[3:]
        elif line.startswith("# "):
            line = line[2:]
        elif line.startswith("|"):
            line = re.sub(r"\s*\|\s*", " | ", line.strip("| "))
        for wrapped in textwrap.wrap(line, width=96) or [""]:
            lines.append(wrapped)
    return lines


def _write_pdf_pack(path: Path, markdown: str) -> None:
    logical_lines = _markdown_to_pdf_lines(markdown)
    lines_per_page = 48
    pages = [
        logical_lines[index:index + lines_per_page]
        for index in range(0, len(logical_lines), lines_per_page)
    ] or [["LPAC / IC Meeting Pack"]]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    kids = []
    for index, page_lines in enumerate(pages):
        page_id = 4 + index * 2
        content_id = page_id + 1
        kids.append(f"{page_id} 0 R")
        text_ops = ["BT", "/F1 9 Tf", "50 760 Td", "12 TL"]
        for line in page_lines:
            text_ops.append(f"({_pdf_escape(line)}) Tj")
            text_ops.append("T*")
        text_ops.append("ET")
        content_stream = "\n".join(text_ops).encode("latin-1", errors="replace")
        objects[content_id] = (
            f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
            + content_stream
            + b"\nendstream"
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode("ascii")

    ordered_ids = sorted(objects)
    payload = bytearray(b"%PDF-1.4\n")
    offsets = {0: 0}
    for object_id in ordered_ids:
        offsets[object_id] = len(payload)
        payload.extend(f"{object_id} 0 obj\n".encode("ascii"))
        payload.extend(objects[object_id])
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {max(ordered_ids) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for object_id in range(1, max(ordered_ids) + 1):
        payload.extend(f"{offsets.get(object_id, 0):010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {max(ordered_ids) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(payload)


def _json_digest(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _packet_revision_id(packet: dict) -> str:
    return (packet.get("scenario_revision") or {}).get("current_revision_id", "")


def _current_scenario_revision_id(simulation_id: str) -> str:
    ledger = _read_revision_ledger(simulation_id)
    return ledger.get("current_revision_id", "")


def _packet_revision_status(simulation_id: str, packet: dict) -> dict:
    packet_revision_id = _packet_revision_id(packet)
    current_revision_id = _current_scenario_revision_id(simulation_id)
    is_stale = bool(packet_revision_id and current_revision_id and packet_revision_id != current_revision_id)
    return {
        "packet_revision_id": packet_revision_id,
        "current_revision_id": current_revision_id,
        "packet_is_stale": is_stale,
        "message": (
            "Governance packet was generated from an older scenario revision. Regenerate packet before approval."
            if is_stale else ""
        ),
    }


def _review_with_revision_status(simulation_id: str, packet: dict, review: dict) -> dict:
    revision_status = _packet_revision_status(simulation_id, packet)
    decorated = dict(review)
    decorated.update(revision_status)
    decorated.setdefault("scenario_revision_id", revision_status["packet_revision_id"])
    if revision_status["packet_is_stale"]:
        decorated["effective_review_status"] = "stale_packet_requires_regeneration"
    else:
        decorated["effective_review_status"] = decorated.get("review_status", "")
    return decorated


def _build_governance_remediation_plan(simulation_id: str, context: dict, packet: dict) -> dict:
    revision_status = _packet_revision_status(simulation_id, packet)
    reserve = context.get("reserve_summary", {})
    financial_plan = context.get("financial_plan", {})
    key_metrics = packet.get("key_metrics", {})
    required_decisions = packet.get("required_decisions", [])
    shortfall = float(reserve.get("shortfall") or key_metrics.get("reserve_shortfall") or 0)
    distribution_amount = float(financial_plan.get("distribution_amount") or key_metrics.get("distributions") or 0)
    capital_call_amount = float(financial_plan.get("capital_call_amount") or key_metrics.get("capital_called") or 0)
    options: list[dict] = []

    if shortfall > 0:
        reduced_distribution = round(max(distribution_amount - shortfall, 0), 2)
        options.append({
            "option_id": "reduce_distribution_to_restore_reserve",
            "option_type": "scenario_patch",
            "recommended": True,
            "owner": "GP",
            "approval_required": "LPAC review before distribution notice",
            "summary": "Reduce planned distribution by the reserve shortfall so projected reserve becomes compliant.",
            "patch": {
                "financial_plan": {
                    "distribution_amount": reduced_distribution,
                }
            },
            "expected_effect": {
                "reserve_shortfall_reduction": round(shortfall, 2),
                "estimated_reserve_shortfall_after": 0,
                "cash_preserved": round(shortfall, 2),
            },
            "evidence_refs": ["report_context.json#reserve_summary", "scenario_patch.json"],
        })
        options.append({
            "option_id": "capital_call_top_up_for_reserve",
            "option_type": "scenario_patch",
            "recommended": False,
            "owner": "GP",
            "approval_required": "Capital call notice and LP review",
            "summary": "Increase called capital enough to cover the current reserve shortfall while preserving the planned distribution.",
            "patch": {
                "financial_plan": {
                    "capital_call_amount": round(capital_call_amount + shortfall, 2),
                }
            },
            "expected_effect": {
                "additional_capital_call": round(shortfall, 2),
                "estimated_reserve_shortfall_after": 0,
                "distribution_amount_preserved": distribution_amount,
            },
            "evidence_refs": ["report_context.json#cashflow_summary", "fund_terms.yaml#capital_call_notice"],
        })
        options.append({
            "option_id": "lpac_reserve_waiver",
            "option_type": "governance_review_action",
            "recommended": False,
            "owner": "LPAC",
            "approval_required": "LPAC waiver",
            "summary": "Record an LPAC reserve waiver without changing executable scenario inputs.",
            "review_action": "waive_reserve",
            "expected_effect": {
                "ledger_changes": 0,
                "reserve_shortfall_after": round(shortfall, 2),
                "waiver_required": True,
            },
            "evidence_refs": ["governance_packet.json#required_decisions.reserve_shortfall_resolution"],
        })

    for decision in required_decisions:
        if decision.get("decision_id") == "highest_risk_branch_response":
            options.append({
                "option_id": "highest_risk_branch_action_plan",
                "option_type": "governance_action",
                "recommended": shortfall <= 0,
                "owner": decision.get("owner", "GP"),
                "approval_required": "GP governance review",
                "summary": decision.get("decision", "Review highest-risk branch and record action plan."),
                "expected_effect": {
                    "risk_branch": packet.get("highest_risk_branch", {}).get("branch_id", ""),
                    "risk_level": packet.get("highest_risk_branch", {}).get("risk_level", ""),
                    "scenario_patch_required": False,
                },
                "evidence_refs": decision.get("evidence_refs", []),
            })

    if not options:
        options.append({
            "option_id": "standard_closeout",
            "option_type": "governance_action",
            "recommended": True,
            "owner": "GP",
            "approval_required": "Standard review",
            "summary": "Proceed with standard packet approval and evidence archive.",
            "expected_effect": {
                "scenario_patch_required": False,
                "reserve_shortfall_after": 0,
            },
            "evidence_refs": ["governance_packet.json", "business_report.md"],
        })

    return {
        "schema_version": "0.1",
        "plan_type": "governance_remediation_plan",
        "simulation_id": simulation_id,
        "generated_at": datetime.utcnow().isoformat(),
        "generated_from_packet_digest": _json_digest(packet),
        "scenario_revision": {
            "packet_revision_id": revision_status["packet_revision_id"],
            "current_revision_id": revision_status["current_revision_id"],
            "packet_is_stale": revision_status["packet_is_stale"],
        },
        "status": "blocked_stale_packet" if revision_status["packet_is_stale"] else "ready_for_review",
        "adoption_allowed": not revision_status["packet_is_stale"],
        "blocked_reason": revision_status["message"],
        "required_decisions_count": len(required_decisions),
        "reserve_shortfall": round(shortfall, 2),
        "recommended_option_id": next((item["option_id"] for item in options if item.get("recommended")), options[0]["option_id"]),
        "options": options,
    }


def _find_remediation_option(plan: dict, option_id: str) -> dict:
    for option in plan.get("options", []):
        if option.get("option_id") == option_id:
            return option
    raise ValueError(f"Remediation option not found: {option_id}")


def _remediation_plan_adoption_status(simulation_id: str, plan: dict) -> dict:
    plan_revision_id = (plan.get("scenario_revision") or {}).get("current_revision_id", "")
    current_revision_id = _current_scenario_revision_id(simulation_id)
    is_stale = bool(plan_revision_id and current_revision_id and plan_revision_id != current_revision_id)
    blocked_reason = ""
    if plan.get("adoption_allowed") is False:
        blocked_reason = plan.get("blocked_reason") or "Remediation plan is not adoption-ready."
    elif is_stale:
        blocked_reason = "Remediation plan was generated from an older scenario revision. Regenerate remediation plan before adoption."
    return {
        "plan_revision_id": plan_revision_id,
        "current_revision_id": current_revision_id,
        "plan_is_stale": is_stale,
        "adoption_allowed": plan.get("adoption_allowed") is not False and not is_stale,
        "blocked_reason": blocked_reason,
    }


def _new_governance_review(packet: dict, packet_digest: str) -> dict:
    now = datetime.utcnow().isoformat()
    scenario_revision = packet.get("scenario_revision") or {}
    return {
        "schema_version": "0.1",
        "review_type": "governance_packet_review",
        "simulation_id": packet.get("simulation_id", ""),
        "packet_digest": packet_digest,
        "packet_generated_at": packet.get("generated_at", ""),
        "packet_decision_status": packet.get("decision_status", ""),
        "scenario_revision_id": scenario_revision.get("current_revision_id", ""),
        "review_status": "pending_review",
        "current_step": "LPAC_review" if packet.get("decision_status") == "action_required" else "GP_review",
        "requires_rerun": False,
        "approved_actions": [],
        "review_log": [],
        "created_at": now,
        "updated_at": now,
    }


def _read_or_create_governance_review(simulation_id: str, packet: dict) -> dict:
    review_path = _business_dir(simulation_id) / "governance_review.json"
    packet_digest = _json_digest(packet)
    if review_path.exists():
        review = _read_json(review_path)
        if review.get("packet_digest") == packet_digest:
            review.setdefault("scenario_revision_id", _packet_revision_id(packet))
            return review
    review = _new_governance_review(packet, packet_digest)
    write_json(review_path, review)
    return review


def _apply_governance_review_action(review: dict, packet: dict, data: dict) -> dict:
    action = (data.get("action") or "").strip()
    actor = (data.get("actor") or "Human reviewer").strip()
    role = (data.get("role") or "Reviewer").strip()
    note = (data.get("note") or "").strip()
    valid_actions = {"approve", "waive_reserve", "request_rerun", "reject", "reset_pending"}
    if action not in valid_actions:
        raise ValueError(f"Unsupported review action: {action}")

    now = datetime.utcnow().isoformat()
    log_entry = {
        "action": action,
        "actor": actor,
        "role": role,
        "note": note,
        "packet_digest": review.get("packet_digest", ""),
        "created_at": now,
    }

    if action == "approve":
        review["review_status"] = "approved"
        review["current_step"] = "closed"
        review["requires_rerun"] = False
        review.setdefault("approved_actions", []).append({
            "type": "packet_approved",
            "actor": actor,
            "role": role,
            "created_at": now,
            "scope": "governance_packet",
        })
    elif action == "waive_reserve":
        review["review_status"] = "approved_with_reserve_waiver"
        review["current_step"] = "closed"
        review["requires_rerun"] = False
        reserve_shortfall = packet.get("key_metrics", {}).get("reserve_shortfall", 0)
        review.setdefault("approved_actions", []).append({
            "type": "reserve_waiver",
            "actor": actor,
            "role": role,
            "created_at": now,
            "reserve_shortfall": reserve_shortfall,
            "scope": "reserve_shortfall_resolution",
        })
    elif action == "request_rerun":
        review["review_status"] = "rerun_requested"
        review["current_step"] = "scenario_revision"
        review["requires_rerun"] = True
    elif action == "reject":
        review["review_status"] = "rejected"
        review["current_step"] = "scenario_revision"
        review["requires_rerun"] = True
    elif action == "reset_pending":
        review["review_status"] = "pending_review"
        review["current_step"] = "LPAC_review" if packet.get("decision_status") == "action_required" else "GP_review"
        review["requires_rerun"] = False

    review.setdefault("review_log", []).append(log_entry)
    review["updated_at"] = now
    return review


@business_simulation_bp.route("/<simulation_id>/report", methods=["POST"])
def generate_business_markdown_report(simulation_id: str):
    """Generate a deterministic markdown report from report_context.json."""
    try:
        context_path = _business_dir(simulation_id) / "report_context.json"
        if not context_path.exists():
            return jsonify({
                "success": False,
                "error": f"Report context not found for {simulation_id}"
            }), 404

        context = _read_json(context_path)
        markdown = _build_markdown_report(context)
        report_path = _business_dir(simulation_id) / "business_report.md"
        report_path.write_text(markdown, encoding="utf-8")

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "report_path": str(report_path),
                "bytes": report_path.stat().st_size,
                "preview": markdown[:1000],
            }
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Business markdown report generation failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/governance-packet", methods=["POST"])
def generate_business_governance_packet(simulation_id: str):
    """Generate deterministic LPAC/IC governance packet outputs."""
    try:
        context_path = _business_dir(simulation_id) / "report_context.json"
        if not context_path.exists():
            return jsonify({
                "success": False,
                "error": f"Report context not found for {simulation_id}"
            }), 404

        context = _read_json(context_path)
        packet = _build_governance_packet(context)
        memo = _build_governance_memo(packet)
        packet_path = _business_dir(simulation_id) / "governance_packet.json"
        memo_path = _business_dir(simulation_id) / "governance_memo.md"
        write_json(packet_path, packet)
        memo_path.write_text(memo, encoding="utf-8")
        review = _read_or_create_governance_review(simulation_id, packet)
        decorated_review = _review_with_revision_status(simulation_id, packet, review)

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "packet_path": str(packet_path),
                "memo_path": str(memo_path),
                "decision_status": packet.get("decision_status"),
                "scenario_revision_id": _packet_revision_id(packet),
                "highest_risk_branch": packet.get("highest_risk_branch", {}),
                "required_decisions_count": len(packet.get("required_decisions", [])),
                "review_status": decorated_review.get("effective_review_status"),
                "packet_is_stale": decorated_review.get("packet_is_stale", False),
                "review_path": str(_business_dir(simulation_id) / "governance_review.json"),
                "bytes": {
                    "packet": packet_path.stat().st_size,
                    "memo": memo_path.stat().st_size,
                },
                "preview": memo[:1000],
            }
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Business governance packet generation failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/meeting-pack", methods=["POST"])
def generate_business_meeting_pack(simulation_id: str):
    """Generate LPAC / IC meeting pack exports from current governance outputs."""
    try:
        business_dir = _business_dir(simulation_id)
        context_path = business_dir / "report_context.json"
        if not context_path.exists():
            return jsonify({
                "success": False,
                "error": f"Report context not found for {simulation_id}"
            }), 404

        context = _read_json(context_path)
        packet_path = business_dir / "governance_packet.json"
        memo_path = business_dir / "governance_memo.md"
        if packet_path.exists():
            packet = _read_json(packet_path)
        else:
            packet = _build_governance_packet(context)
            write_json(packet_path, packet)
            memo_path.write_text(_build_governance_memo(packet), encoding="utf-8")

        review = _read_or_create_governance_review(simulation_id, packet)
        decorated_review = _review_with_revision_status(simulation_id, packet, review)
        evidence_path = business_dir / "evidence_bindings.json"
        evidence_bindings = _read_json(evidence_path) if evidence_path.exists() else context.get("evidence_bindings", {})

        pack = _build_meeting_pack(simulation_id, context, packet, decorated_review, evidence_bindings)
        markdown = _build_meeting_pack_markdown(pack)
        pack_path = business_dir / "meeting_pack.json"
        markdown_path = business_dir / "meeting_pack.md"
        docx_path = business_dir / "meeting_pack.docx"
        pdf_path = business_dir / "meeting_pack.pdf"
        write_json(pack_path, pack)
        markdown_path.write_text(markdown, encoding="utf-8")
        _write_docx_pack(docx_path, markdown)
        _write_pdf_pack(pdf_path, markdown)

        files = {
            "json": {"path": str(pack_path), "bytes": pack_path.stat().st_size},
            "markdown": {"path": str(markdown_path), "bytes": markdown_path.stat().st_size},
            "docx": {"path": str(docx_path), "bytes": docx_path.stat().st_size},
            "pdf": {"path": str(pdf_path), "bytes": pdf_path.stat().st_size},
        }
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "pack_type": pack.get("pack_type"),
                "generation_policy": pack.get("generation_policy"),
                "decision_status": pack.get("packet_status", {}).get("decision_status"),
                "review_status": pack.get("packet_status", {}).get("review_status"),
                "lp_readiness_status": pack.get("lp_capital_brief", {}).get("lp_readiness_status"),
                "agenda_count": len(pack.get("meeting", {}).get("agenda", [])),
                "decision_count": len(pack.get("decision_table", [])),
                "risk_count": len(pack.get("risk_appendix", [])),
                "evidence_count": len(pack.get("evidence_appendix", [])),
                "files": files,
                "preview": markdown[:1200],
            }
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Business meeting pack generation failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/governance-review", methods=["GET"])
def get_business_governance_review(simulation_id: str):
    """Return governance packet review state."""
    try:
        packet_path = _business_dir(simulation_id) / "governance_packet.json"
        if not packet_path.exists():
            return jsonify({
                "success": False,
                "error": f"Governance packet not found for {simulation_id}",
            }), 404
        packet = _read_json(packet_path)
        review = _read_or_create_governance_review(simulation_id, packet)
        return jsonify({"success": True, "data": _review_with_revision_status(simulation_id, packet, review)})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Reading governance review failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/governance-remediation-plan", methods=["GET"])
def get_business_governance_remediation_plan(simulation_id: str):
    """Return the latest generated remediation plan."""
    try:
        plan_path = _business_dir(simulation_id) / "governance_remediation_plan.json"
        if not plan_path.exists():
            return jsonify({
                "success": False,
                "error": f"Governance remediation plan not found for {simulation_id}",
            }), 404
        return jsonify({"success": True, "data": _read_json(plan_path)})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Reading governance remediation plan failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/governance-remediation-plan", methods=["POST"])
def generate_business_governance_remediation_plan(simulation_id: str):
    """Generate revision-bound remediation options from packet and report context."""
    try:
        business_dir = _business_dir(simulation_id)
        packet_path = business_dir / "governance_packet.json"
        context_path = business_dir / "report_context.json"
        plan_path = business_dir / "governance_remediation_plan.json"
        if not packet_path.exists():
            return jsonify({
                "success": False,
                "error": f"Governance packet not found for {simulation_id}",
            }), 404
        if not context_path.exists():
            return jsonify({
                "success": False,
                "error": f"Report context not found for {simulation_id}",
            }), 404

        packet = _read_json(packet_path)
        context = _read_json(context_path)
        plan = _build_governance_remediation_plan(simulation_id, context, packet)
        write_json(plan_path, plan)
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "plan_path": str(plan_path),
                "status": plan.get("status"),
                "adoption_allowed": plan.get("adoption_allowed"),
                "scenario_revision": plan.get("scenario_revision", {}),
                "recommended_option_id": plan.get("recommended_option_id"),
                "options_count": len(plan.get("options", [])),
                "preview": plan,
            }
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Generating governance remediation plan failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/governance-remediation-plan/options/<option_id>/preview", methods=["POST"])
def preview_business_governance_remediation_option(simulation_id: str, option_id: str):
    """Preview the scenario patch represented by a remediation option."""
    try:
        business_dir = _business_dir(simulation_id)
        plan_path = business_dir / "governance_remediation_plan.json"
        scenario_path = business_dir / "scenario.yaml"
        fund_terms_path = business_dir / "fund_terms.yaml"
        patch_path = business_dir / "scenario_patch.json"
        if not plan_path.exists():
            return jsonify({"success": False, "error": f"Governance remediation plan not found for {simulation_id}"}), 404
        if not scenario_path.exists() or not fund_terms_path.exists():
            return jsonify({"success": False, "error": f"Business simulation inputs not found for {simulation_id}"}), 404

        plan = _read_json(plan_path)
        adoption_status = _remediation_plan_adoption_status(simulation_id, plan)
        if not adoption_status["adoption_allowed"]:
            return jsonify({"success": False, "error": adoption_status["blocked_reason"], "data": adoption_status}), 409
        option = _find_remediation_option(plan, option_id)
        if option.get("option_type") != "scenario_patch":
            return jsonify({
                "success": False,
                "error": f"Remediation option is not a scenario patch: {option_id}",
            }), 400

        patch = _normalize_scenario_patch({"patch": option.get("patch") or {}})
        scenario = load_structured_file(scenario_path)
        fund_terms = load_structured_file(fund_terms_path)
        preview = _build_scenario_patch_preview(simulation_id, fund_terms, scenario, patch)
        preview["source"] = {
            "type": "governance_remediation_option",
            "option_id": option_id,
            "plan_digest": _json_digest(plan),
        }
        preview["remediation_option"] = option
        write_json(patch_path, preview)
        return jsonify({"success": True, "data": preview})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Previewing governance remediation option failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/governance-remediation-plan/options/<option_id>/commit", methods=["POST"])
def commit_business_governance_remediation_option(simulation_id: str, option_id: str):
    """Commit a remediation scenario-patch option into executable inputs."""
    try:
        business_dir = _business_dir(simulation_id)
        plan_path = business_dir / "governance_remediation_plan.json"
        scenario_path = business_dir / "scenario.yaml"
        fund_terms_path = business_dir / "fund_terms.yaml"
        patch_path = business_dir / "scenario_patch.json"
        run_state_path = _simulation_dir(simulation_id) / "run_state.json"
        if not plan_path.exists():
            return jsonify({"success": False, "error": f"Governance remediation plan not found for {simulation_id}"}), 404
        if not scenario_path.exists() or not fund_terms_path.exists():
            return jsonify({"success": False, "error": f"Business simulation inputs not found for {simulation_id}"}), 404

        plan = _read_json(plan_path)
        adoption_status = _remediation_plan_adoption_status(simulation_id, plan)
        if not adoption_status["adoption_allowed"]:
            return jsonify({"success": False, "error": adoption_status["blocked_reason"], "data": adoption_status}), 409
        option = _find_remediation_option(plan, option_id)
        if option.get("option_type") != "scenario_patch":
            return jsonify({
                "success": False,
                "error": f"Remediation option is not a scenario patch: {option_id}",
            }), 400

        patch = _normalize_scenario_patch({"patch": option.get("patch") or {}})
        scenario = load_structured_file(scenario_path)
        fund_terms = load_structured_file(fund_terms_path)
        committed = _apply_scenario_patch(simulation_id, fund_terms, scenario, patch)
        committed["source"] = {
            "type": "governance_remediation_option",
            "option_id": option_id,
            "plan_digest": _json_digest(plan),
        }
        committed["remediation_option"] = option

        _write_yaml(fund_terms_path, fund_terms)
        _write_yaml(scenario_path, scenario)
        write_json(patch_path, committed)
        revision = _append_scenario_revision(
            simulation_id,
            change_type="remediation_option_commit",
            summary=f"Committed remediation option {option_id} into executable scenario inputs.",
            changed_paths=committed.get("changed_paths", []),
            source={
                "remediation_option_id": option_id,
                "governance_remediation_plan_file": "governance_remediation_plan.json",
                "scenario_patch_file": "scenario_patch.json",
                "plan_digest": _json_digest(plan),
            },
        )
        committed["revision"] = revision
        write_json(patch_path, committed)

        run_state = _read_json(run_state_path) if run_state_path.exists() else {}
        run_state.update({
            "simulation_id": simulation_id,
            "engine_type": "business_governance",
            "runner_status": "idle",
            "pending_change": "remediation_option_committed",
            "updated_at": datetime.utcnow().isoformat(),
        })
        write_json(run_state_path, run_state)
        return jsonify({"success": True, "data": committed})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Committing governance remediation option failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/governance-review", methods=["POST"])
def update_business_governance_review(simulation_id: str):
    """Apply a human governance review action to the packet state."""
    try:
        packet_path = _business_dir(simulation_id) / "governance_packet.json"
        review_path = _business_dir(simulation_id) / "governance_review.json"
        if not packet_path.exists():
            return jsonify({
                "success": False,
                "error": f"Governance packet not found for {simulation_id}",
            }), 404
        packet = _read_json(packet_path)
        review = _read_or_create_governance_review(simulation_id, packet)
        data = request.get_json(silent=True) or {}
        action = (data.get("action") or "").strip()
        revision_status = _packet_revision_status(simulation_id, packet)
        if revision_status["packet_is_stale"] and action in {"approve", "waive_reserve"}:
            return jsonify({
                "success": False,
                "error": revision_status["message"],
                "data": revision_status,
            }), 409
        review = _apply_governance_review_action(review, packet, data)
        write_json(review_path, review)
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "review": _review_with_revision_status(simulation_id, packet, review),
                "review_path": str(review_path),
            }
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Updating governance review failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@business_simulation_bp.route("/<simulation_id>/outputs/<filename>", methods=["GET"])
def get_business_output_file(simulation_id: str, filename: str):
    """Return a JSON/JSONL output file as parsed records."""
    try:
        if filename not in ALLOWED_OUTPUT_FILES:
            return jsonify({"success": False, "error": "Output file is not allowed"}), 400

        output_path = _business_dir(simulation_id) / filename
        if not output_path.exists():
            if filename in {"business_report.md", "governance_memo.md"}:
                return jsonify({
                    "success": True,
                    "data": {"content": "", "bytes": 0, "missing": True}
                })
            return jsonify({"success": False, "error": f"Output not found: {filename}"}), 404

        if output_path.suffix == ".md":
            data = {
                "content": output_path.read_text(encoding="utf-8"),
                "bytes": output_path.stat().st_size,
            }
        elif output_path.suffix == ".jsonl":
            records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            data = {"records": records, "count": len(records)}
        else:
            data = _read_json(output_path)

        return jsonify({"success": True, "data": data})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Reading business output failed: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500
