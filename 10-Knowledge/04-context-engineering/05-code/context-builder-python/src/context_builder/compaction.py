from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredEvent:
    id: str
    tenant: str
    kind: str
    key: str
    value: Any
    sequence: int
    authority: int = 0


def compact_events(events: list[StructuredEvent], tenant: str) -> dict:
    """Keep the strongest scoped event per key; constraints outrank observations."""

    priority = {"constraint": 3, "observation": 2, "pending": 2}
    selected: dict[str, StructuredEvent] = {}
    for event in events:
        if event.tenant != tenant or event.kind not in priority:
            continue
        current = selected.get(event.key)
        rank = (priority[event.kind], event.authority, event.sequence)
        current_rank = (
            (priority[current.kind], current.authority, current.sequence)
            if current
            else None
        )
        if current_rank is None or rank > current_rank:
            selected[event.key] = event
    return {
        "facts": {key: event.value for key, event in selected.items()},
        "sources": {key: event.id for key, event in selected.items()},
        "kinds": {key: event.kind for key, event in selected.items()},
        "method": "scoped-structured-extract-v2",
        "lossy": True,
    }
