"""Pydantic models for the MVP business-governance simulator."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ObjectRef(BaseModel):
    object_type: str
    object_id: str
    qualifier: str = ""


class EventSource(BaseModel):
    kind: Literal["deterministic", "llm_proposal", "external_assumption"] = "deterministic"
    evidence_refs: list[str] = Field(default_factory=list)


class BusinessEvent(BaseModel):
    event_id: str
    timestamp: str
    simulation_time: str
    scenario_id: str
    branch_id: str = "base"
    event_type: str
    actor_agents: list[str] = Field(default_factory=list)
    touched_objects: list[ObjectRef] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    source: EventSource = Field(default_factory=EventSource)
    decision_record_refs: list[str] = Field(default_factory=list)
    rule_execution_refs: list[str] = Field(default_factory=list)
    cashflow_refs: list[str] = Field(default_factory=list)
    ledger_entry_refs: list[str] = Field(default_factory=list)
    state_transition_refs: list[str] = Field(default_factory=list)
    causal_parent_event_refs: list[str] = Field(default_factory=list)


class LedgerLine(BaseModel):
    account: str
    debit: float = 0
    credit: float = 0
    object_id: str | None = None


class LedgerEntry(BaseModel):
    ledger_entry_id: str
    timestamp: str
    simulation_time: str
    event_id: str
    description: str
    lines: list[LedgerLine]

    @property
    def balanced(self) -> bool:
        debit = sum(line.debit for line in self.lines)
        credit = sum(line.credit for line in self.lines)
        return round(debit - credit, 2) == 0


class RuleExecutionRecord(BaseModel):
    rule_execution_id: str
    timestamp: str
    simulation_time: str
    event_id: str
    rule_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    passed: bool = True


class DecisionRecord(BaseModel):
    decision_record_id: str
    timestamp: str
    simulation_time: str
    event_id: str
    decision_type: str
    authority: str
    result: str
    rationale: str
    committed: bool = True
    source: EventSource = Field(default_factory=EventSource)


class RuntimeState(BaseModel):
    simulation_id: str
    scenario_id: str
    branch_id: str = "base"
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None
    current_event_index: int = 0
    funds: dict[str, dict[str, Any]] = Field(default_factory=dict)
    lps: dict[str, dict[str, Any]] = Field(default_factory=dict)
    portfolio_positions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    obligations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    decisions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    lifecycle: dict[str, Any] = Field(default_factory=dict)
    ledger_summary: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    state: RuntimeState
    event_count: int
    ledger_entry_count: int
    decision_count: int
    rule_execution_count: int
