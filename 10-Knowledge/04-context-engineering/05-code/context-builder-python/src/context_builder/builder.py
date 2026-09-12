from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
import math

from .counters import byte_tokens
from .models import (
    BuildResult,
    CandidateRef,
    ContextBudget,
    ContextPolicy,
    ContextRequest,
    LoadedItem,
)


class ContextConflictError(ValueError):
    pass


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed


def _count(counter: Callable[[str], int], text: str) -> int:
    value = counter(text)
    if type(value) is not int or value < 0:
        raise ValueError("token counter must return a non-negative integer")
    return value


def _render_request(request: ContextRequest) -> list[str]:
    rows = [f"[goal] {request.goal}"]
    rows.extend(
        f"[constraint:{index}] {text}"
        for index, text in enumerate(request.constraints, 1)
    )
    rows.extend(
        f"[acceptance:{index}] {text}"
        for index, text in enumerate(request.acceptance, 1)
    )
    return rows


def _render_item(item: LoadedItem) -> str:
    metadata = f"kind={item.ref.kind};trust={item.ref.trust};version={item.ref.version or 'unknown'}"
    return f"[{item.ref.id} | {metadata}] {item.text}"


def _policy_reason(ref: CandidateRef, policy: ContextPolicy) -> str | None:
    if ref.tenant != policy.allowed_tenant:
        return "permission"
    if ref.trust not in policy.allowed_trust:
        return "trust"
    if ref.sensitive and not policy.allow_sensitive:
        return "sensitive"
    if (
        ref.expires_at
        and policy.as_of
        and _parse_time(ref.expires_at) < _parse_time(policy.as_of)
    ):
        return "expired"
    required_version = dict(policy.required_versions).get(ref.kind)
    if required_version is not None and ref.version != required_version:
        return "version"
    return None


def build_context(
    request: ContextRequest,
    candidates: list[CandidateRef],
    loader: Callable[[CandidateRef], str],
    budget: ContextBudget,
    *,
    policy: ContextPolicy | None = None,
    count: Callable[[str], int] = byte_tokens,
) -> BuildResult:
    """Apply metadata policy before reading candidate content, then pack deterministically."""

    policy = policy or ContextPolicy(request.tenant)
    if policy.allowed_tenant != request.tenant:
        raise ValueError("request tenant and policy tenant must match")
    if policy.conflict_mode not in {"error", "warn_keep_both"}:
        raise ValueError("unsupported conflict mode")
    if budget.content_limit < 1:
        raise ValueError("reserved budgets leave no input capacity")
    ids = [item.id for item in candidates]
    if any(not item_id for item_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("candidate ids must be non-empty and unique")
    if any(not math.isfinite(item.utility) for item in candidates):
        raise ValueError("candidate utility must be finite")

    dropped: list[dict[str, str]] = []
    permitted: list[CandidateRef] = []
    for ref in candidates:
        reason = _policy_reason(ref, policy)
        if reason:
            dropped.append({"id": ref.id, "reason": reason})
        else:
            permitted.append(ref)

    loaded: list[LoadedItem] = []
    loaded_ids: list[str] = []
    for ref in permitted:
        text = loader(ref)
        loaded_ids.append(ref.id)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"loader returned invalid content for {ref.id}")
        digest = sha256(text.encode("utf-8")).hexdigest()
        loaded.append(
            LoadedItem(
                ref,
                text,
                _count(count, _render_item(LoadedItem(ref, text, 0, digest))),
                digest,
            )
        )

    transformations: list[dict] = []
    unique: list[LoadedItem] = []
    digest_owner: dict[str, str] = {}
    # Mandatory candidates own an exact duplicate even when the caller supplied
    # an optional copy first. Stable input order breaks ties within each class.
    for item in sorted(loaded, key=lambda value: not value.ref.mandatory):
        if item.digest in digest_owner:
            dropped.append({"id": item.ref.id, "reason": "exact_duplicate"})
            transformations.append(
                {
                    "output_id": digest_owner[item.digest],
                    "source_ids": [digest_owner[item.digest], item.ref.id],
                    "method": "exact_dedup",
                    "lossy": False,
                }
            )
        else:
            digest_owner[item.digest] = item.ref.id
            unique.append(item)

    warnings: list[str] = []
    by_fact: dict[str, list[LoadedItem]] = {}
    for item in unique:
        if item.ref.fact_key:
            by_fact.setdefault(item.ref.fact_key, []).append(item)
    for fact_key, items in by_fact.items():
        if len({item.digest for item in items}) > 1:
            message = f"conflicting candidates for fact_key={fact_key}"
            if policy.conflict_mode == "error":
                raise ContextConflictError(message)
            warnings.append(message)

    request_rows = _render_request(request)
    mandatory = [item for item in unique if item.ref.mandatory]
    optional = [item for item in unique if not item.ref.mandatory]

    def render(items: list[LoadedItem]) -> str:
        return "\n\n".join([*request_rows, *(_render_item(item) for item in items)])

    selected = list(mandatory)
    if _count(count, render(selected)) > budget.content_limit:
        raise ValueError(
            "request and mandatory information exceed budget; do not silently truncate"
        )
    optional.sort(
        key=lambda item: (-item.ref.utility / max(item.tokens, 1), item.ref.id)
    )
    for item in optional:
        if _count(count, render([*selected, item])) <= budget.content_limit:
            selected.append(item)
        else:
            dropped.append({"id": item.ref.id, "reason": "budget"})
    text = render(selected)
    return BuildResult(
        text=text,
        selected_ids=[item.ref.id for item in selected],
        dropped=dropped,
        transformations=transformations,
        warnings=warnings,
        input_tokens=_count(count, text),
        content_limit=budget.content_limit,
        loaded_ids=loaded_ids,
    )
