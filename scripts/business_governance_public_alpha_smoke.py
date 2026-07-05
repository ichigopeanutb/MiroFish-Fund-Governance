#!/usr/bin/env python3
"""Public-alpha smoke test for the MiroFish business-governance module."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
EXAMPLE_SEED_DIR = ROOT / "examples" / "business-governance" / "demo_business"
RUNTIME_SIM_ROOT = BACKEND_DIR / "uploads" / "simulations"
DEFAULT_SIMULATION_ID = "demo_business"


def _ensure_backend_imports() -> None:
    sys.path.insert(0, str(BACKEND_DIR))


def _ensure_demo_seed(simulation_id: str) -> Path:
    target = RUNTIME_SIM_ROOT / simulation_id
    if target.exists():
        return target
    if simulation_id != DEFAULT_SIMULATION_ID:
        raise FileNotFoundError(f"Missing runtime simulation: {target}")
    if not EXAMPLE_SEED_DIR.exists():
        raise FileNotFoundError(f"Missing tracked demo seed: {EXAMPLE_SEED_DIR}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(EXAMPLE_SEED_DIR, target)
    return target


def _post_ok(client, path: str, payload: dict | None = None) -> dict:
    response = client.post(path, json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"POST {path} failed: {response.status_code} {response.get_data(as_text=True)}")
    data = response.get_json()
    if not data or not data.get("success"):
        raise RuntimeError(f"POST {path} returned unsuccessful payload: {data}")
    return data["data"]


def _get_ok(client, path: str) -> dict:
    response = client.get(path)
    if response.status_code != 200:
        raise RuntimeError(f"GET {path} failed: {response.status_code} {response.get_data(as_text=True)}")
    data = response.get_json()
    if not data or not data.get("success"):
        raise RuntimeError(f"GET {path} returned unsuccessful payload: {data}")
    return data["data"]


def _validate_delivery_files(files: dict) -> dict:
    docx_path = Path(files["docx"]["path"])
    pdf_path = Path(files["pdf"]["path"])
    with zipfile.ZipFile(docx_path) as archive:
        if "word/document.xml" not in archive.namelist():
            raise RuntimeError(f"DOCX is missing word/document.xml: {docx_path}")
    if not pdf_path.read_bytes().startswith(b"%PDF-1.4"):
        raise RuntimeError(f"PDF does not start with a PDF header: {pdf_path}")
    return {
        "docx_bytes": docx_path.stat().st_size,
        "pdf_bytes": pdf_path.stat().st_size,
    }


def _repo_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _public_file_metadata(files: dict) -> dict:
    public_files = {}
    for key, value in files.items():
        public_files[key] = {
            "bytes": value.get("bytes", 0),
            "path": _repo_path(value.get("path", "")),
        }
    return public_files


def run_smoke(simulation_id: str) -> dict:
    _ensure_backend_imports()
    from app import create_app

    simulation_dir = _ensure_demo_seed(simulation_id)
    client = create_app().test_client()

    run_data = _post_ok(client, "/api/business-simulation/run", {"simulation_id": simulation_id})
    report_data = _post_ok(client, f"/api/business-simulation/{simulation_id}/report")
    packet_data = _post_ok(client, f"/api/business-simulation/{simulation_id}/governance-packet")
    pack_data = _post_ok(client, f"/api/business-simulation/{simulation_id}/meeting-pack")

    branch_results = _get_ok(client, f"/api/business-simulation/{simulation_id}/outputs/branch_results.json")
    report_context = _get_ok(client, f"/api/business-simulation/{simulation_id}/outputs/report_context.json")
    meeting_pack = _get_ok(client, f"/api/business-simulation/{simulation_id}/outputs/meeting_pack.json")
    delivery = _validate_delivery_files(pack_data["files"])

    branch_count = branch_results.get("scenario_expansion", {}).get("branch_count")
    if branch_count != 12:
        raise RuntimeError(f"Expected 12 branch scenarios, got {branch_count}")
    if meeting_pack.get("pack_type") != "lpac_ic_meeting_pack":
        raise RuntimeError(f"Unexpected meeting pack type: {meeting_pack.get('pack_type')}")
    if report_context.get("evidence_bindings", {}).get("binding_policy") != "evidence_only_does_not_mutate_ledger":
        raise RuntimeError("Evidence binding policy mismatch")

    return {
        "schema_version": "0.1",
        "status": "passed",
        "simulation_id": simulation_id,
        "runtime_simulation_dir": _repo_path(simulation_dir),
        "events": run_data.get("events"),
        "ledger_balanced": run_data.get("ledger_balanced"),
        "decision_status": packet_data.get("decision_status"),
        "review_status": packet_data.get("review_status"),
        "meeting_pack_type": meeting_pack.get("pack_type"),
        "lp_readiness_status": meeting_pack.get("lp_capital_brief", {}).get("lp_readiness_status"),
        "scenario_expansion": branch_results.get("scenario_expansion", {}),
        "highest_risk_branch": branch_results.get("risk_summary", [{}])[0],
        "evidence_bindings_count": report_context.get("evidence_bindings", {}).get("bindings_count"),
        "meeting_pack_files": _public_file_metadata(pack_data.get("files", {})),
        "delivery_file_check": delivery,
        "report_bytes": report_data.get("bytes"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the business-governance public alpha smoke test.")
    parser.add_argument("--simulation-id", default=DEFAULT_SIMULATION_ID)
    parser.add_argument("--write-summary", help="Optional JSON file path for a public example summary.")
    args = parser.parse_args()

    summary = run_smoke(args.simulation_id)
    if args.write_summary:
        summary_path = Path(args.write_summary)
        if not summary_path.is_absolute():
            summary_path = ROOT / summary_path
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary["summary_path"] = str(summary_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
