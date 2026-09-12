"""Compatibility helpers for older notebook links.

New teaching code should import the versioned reference package in ``05-code``.
These wrappers preserve the original tiny API while sharing its fixed metrics and
compaction semantics.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import sys

PACKAGE_SRC = Path(__file__).parents[1] / "05-code" / "context-builder-python" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from context_builder import (  # noqa: E402
    CandidateRef,
    ContextBudget,
    ContextRequest,
    StructuredEvent,
    build_context,
    byte_tokens,
    compact_events,
    evidence_metrics,
)


@dataclass(frozen=True)
class Item:
    id: str
    text: str
    utility: float
    mandatory: bool = False
    tenant: str = "alpha"


def pack(
    items: list[Item],
    window: int,
    reserved_output: int,
    tenant: str,
    count=byte_tokens,
) -> dict:
    """Adapt the original in-memory fixture to the read-gated builder API."""

    refs = [
        CandidateRef(
            id=item.id,
            tenant=item.tenant,
            kind="teaching_fixture",
            trust="workspace",
            utility=item.utility,
            mandatory=item.mandatory,
        )
        for item in items
    ]
    content = {item.id: item.text for item in items}
    result = build_context(
        ContextRequest(goal="legacy notebook request", tenant=tenant),
        refs,
        lambda ref: content[ref.id],
        ContextBudget(window, reserved_output),
        count=count,
    )
    return {
        "text": result.text,
        "selected_ids": result.selected_ids,
        "dropped": result.dropped,
        "input_tokens": result.input_tokens,
        "input_limit": result.content_limit,
        "counting": "injected counter (default: UTF-8 byte tokenizer)",
    }


def compact(events: list[dict], tenant: str = "alpha") -> dict:
    """Adapt structured dictionaries; unsupported logs stay in source storage."""

    structured = [
        StructuredEvent(
            id=event["id"],
            tenant=event.get("tenant", tenant),
            kind=event["kind"],
            key=event.get("key", ""),
            value=event.get("value"),
            sequence=index,
        )
        for index, event in enumerate(events)
    ]
    return compact_events(structured, tenant)


def recall(summary: dict, expected: dict) -> float | None:
    selected = {
        key
        for key, value in summary.get("facts", {}).items()
        if expected.get(key) == value
    }
    return evidence_metrics(set(expected), selected).recall


def serialized(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
