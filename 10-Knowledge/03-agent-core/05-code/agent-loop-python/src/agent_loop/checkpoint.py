"""Portable JSON checkpoints for the teaching state model."""

from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4

from .models import Action, AgentState, StepRecord, Usage


def save_checkpoint(state: AgentState, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(asdict(state), ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(target)


def load_checkpoint(path: str | Path) -> AgentState:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["usage"] = Usage(**data.get("usage", {}))
    data["history"] = [
        StepRecord(
            Action(**item["action"]),
            item["observation"],
            item["started_at"],
            item["duration_ms"],
        )
        for item in data.get("history", [])
    ]
    return AgentState(**data)
