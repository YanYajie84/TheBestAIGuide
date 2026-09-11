"""Minimal explicit plan objects; accepted artifacts survive replanning."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PlanStep:
    id: str
    query: str
    depends_on: tuple[str, ...] = ()
    acceptance: str = ""
    status: str = "pending"
    artifact: Any = None


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)
    version: int = 1


def execute_plan(
    plan: Plan,
    execute: Callable[[PlanStep], Any],
    accept: Callable[[PlanStep, Any], bool],
) -> Plan:
    result = deepcopy(plan)
    known = {step.id for step in result.steps}
    if len(known) != len(result.steps) or any(
        dep not in known for step in result.steps for dep in step.depends_on
    ):
        raise ValueError("plan ids must be unique and dependencies must exist")
    while True:
        ready = [
            step
            for step in result.steps
            if step.status == "pending"
            and all(
                next(s for s in result.steps if s.id == dep).status == "accepted"
                for dep in step.depends_on
            )
        ]
        if not ready:
            break
        for step in ready:
            artifact = execute(deepcopy(step))
            step.artifact = artifact
            step.status = (
                "accepted" if accept(deepcopy(step), artifact) else "missing_evidence"
            )
    for step in result.steps:
        if step.status == "pending":
            step.status = "blocked"
    return result


def replan(previous: Plan, proposed_steps: list[PlanStep]) -> Plan:
    accepted = {
        step.id: deepcopy(step) for step in previous.steps if step.status == "accepted"
    }
    merged = [accepted.get(step.id, deepcopy(step)) for step in proposed_steps]
    return Plan(merged, previous.version + 1)
