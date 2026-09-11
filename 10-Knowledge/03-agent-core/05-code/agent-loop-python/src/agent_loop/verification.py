"""Small, bounded verification helpers for teaching revision loops."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RevisionResult:
    candidate: str
    verdict: dict[str, Any]
    attempts: int


def run_revision_loop(
    generate: Callable[[dict[str, Any] | None], str],
    verify: Callable[[str], dict[str, Any]],
    *,
    max_revisions: int = 1,
) -> RevisionResult:
    if max_revisions < 0:
        raise ValueError("max_revisions cannot be negative")
    feedback = None
    for attempt in range(1, max_revisions + 2):
        candidate = generate(feedback)
        verdict = verify(candidate)
        if verdict.get("passed") is True or attempt == max_revisions + 1:
            return RevisionResult(candidate, verdict, attempt)
        feedback = verdict
    raise AssertionError("bounded loop must return")
