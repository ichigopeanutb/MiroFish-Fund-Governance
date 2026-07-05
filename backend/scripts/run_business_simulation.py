#!/usr/bin/env python3
"""Run the MiroFish business-governance simulation engine."""

from __future__ import annotations

import argparse
import os
import sys

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, ".."))
sys.path.insert(0, _backend_dir)

from app.services.business_simulation import BusinessSimulationEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a business-governance fund simulation")
    parser.add_argument("--config", required=True, help="Path to business_simulation_config.json")
    args = parser.parse_args()

    engine = BusinessSimulationEngine(args.config)
    result = engine.run()
    print("Business-governance simulation completed")
    print(f"simulation_id: {result.state.simulation_id}")
    print(f"events: {result.event_count}")
    print(f"ledger_entries: {result.ledger_entry_count}")
    print(f"decisions: {result.decision_count}")
    print(f"rules: {result.rule_execution_count}")
    print(f"ledger_balanced: {result.state.ledger_summary.get('balanced')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
