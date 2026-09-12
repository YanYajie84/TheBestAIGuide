from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextRequest:
    goal: str
    tenant: str
    constraints: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateRef:
    """Metadata available before protected content is read."""

    id: str
    tenant: str
    kind: str
    trust: str
    utility: float
    mandatory: bool = False
    version: str = ""
    expires_at: str | None = None
    sensitive: bool = False
    fact_key: str | None = None
    authority: int = 0


@dataclass(frozen=True)
class ContextPolicy:
    allowed_tenant: str
    allowed_trust: frozenset[str] = frozenset(
        {"system", "user", "workspace", "runtime"}
    )
    allow_sensitive: bool = False
    as_of: str | None = None
    conflict_mode: str = "error"
    required_versions: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ContextBudget:
    window_tokens: int
    reserved_output_tokens: int
    reserved_protocol_tokens: int = 0
    reserved_tool_tokens: int = 0

    @property
    def content_limit(self) -> int:
        return (
            self.window_tokens
            - self.reserved_output_tokens
            - self.reserved_protocol_tokens
            - self.reserved_tool_tokens
        )


@dataclass(frozen=True)
class LoadedItem:
    ref: CandidateRef
    text: str
    tokens: int
    digest: str


@dataclass
class BuildResult:
    text: str
    selected_ids: list[str]
    dropped: list[dict[str, str]]
    transformations: list[dict[str, Any]]
    warnings: list[str]
    input_tokens: int
    content_limit: int
    loaded_ids: list[str] = field(default_factory=list)
