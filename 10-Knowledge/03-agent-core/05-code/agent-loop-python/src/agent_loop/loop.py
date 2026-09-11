from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from time import perf_counter
from typing import Callable
from uuid import uuid4

from .models import Action, AgentState, Model, ModelDecision, StepRecord, Usage
from .tools import Tool
from .trace import write_trace


@dataclass(frozen=True)
class ApprovalDecision:
    decision_id: str
    approved: bool


def _validate_json(value) -> None:
    """Reject Python-only values before tracing or canonical signatures."""
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        for item in value.values():
            _validate_json(item)
    elif isinstance(value, list):
        for item in value:
            _validate_json(item)
    elif value is None or type(value) in {str, bool, int, float}:
        json.dumps(value, allow_nan=False)
    else:
        raise ValueError("value is not JSON data")


def _action_data(action: Action) -> dict:
    return {
        "kind": action.kind,
        "name": action.name,
        "arguments": deepcopy(action.arguments),
        "answer": action.answer,
    }


def _action_digest(action: Action) -> str:
    payload = json.dumps(
        _action_data(action), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _run_tool(
    tool: Tool, arguments: dict
) -> tuple[bool, object | None, str | None, bool]:
    if tool.side_effecting and tool.require_idempotency_key:
        key = arguments.get("idempotency_key")
        if not isinstance(key, str) or not key.strip():
            return False, None, "idempotency_key_required", False
    if tool.timeout_seconds is None:
        try:
            return True, tool.handler(deepcopy(arguments)), None, False
        except ValueError:
            return False, None, "invalid_arguments", False
        except Exception:
            return False, None, "execution_error", False

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-tool")
    future = executor.submit(tool.handler, deepcopy(arguments))
    try:
        return True, future.result(timeout=tool.timeout_seconds), None, False
    except FutureTimeout:
        future.cancel()
        code = "timeout_side_effect_unknown" if tool.side_effecting else "timeout"
        return False, None, code, tool.side_effecting
    except ValueError:
        return False, None, "invalid_arguments", False
    except Exception:
        return False, None, "execution_error", False
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _execute_action(
    state: AgentState, action: Action, tools: dict[str, Tool], event
) -> dict:
    call_id = f"{state.run_id}:{state.steps}"
    event(
        "tool_call",
        {"call_id": call_id, "name": action.name, "arguments": action.arguments},
    )
    started_at = datetime.now(timezone.utc).isoformat()
    started = perf_counter()
    tool = tools.get(action.name)
    if tool is None:
        result = {
            "call_id": call_id,
            "ok": False,
            "error": {"code": "unknown_tool", "retryable": False},
        }
    elif not tool.allowed:
        result = {
            "call_id": call_id,
            "ok": False,
            "error": {"code": "permission_denied", "retryable": False},
        }
    else:
        ok, data, error_code, uncertain = _run_tool(tool, action.arguments)
        if ok:
            try:
                _validate_json(data)
                result = {"call_id": call_id, "ok": True, "data": deepcopy(data)}
            except Exception:
                result = {
                    "call_id": call_id,
                    "ok": False,
                    "error": {"code": "invalid_output", "retryable": False},
                }
        else:
            retryable = error_code == "timeout" and not uncertain
            result = {
                "call_id": call_id,
                "ok": False,
                "error": {"code": error_code, "retryable": retryable},
            }
            if uncertain:
                result["error"]["side_effect_unknown"] = True
    duration_ms = max(0, round((perf_counter() - started) * 1000))
    state.observations.append(deepcopy(result))
    state.history.append(
        StepRecord(deepcopy(action), deepcopy(result), started_at, duration_ms)
    )
    event("tool_result", {**deepcopy(result), "duration_ms": duration_ms})
    return result


def _drive(
    model: Model,
    tools: dict[str, Tool],
    state: AgentState,
    *,
    max_steps: int,
    repeat_limit: int,
    trace_path: str | None,
    max_total_tokens: int | None,
    should_cancel: Callable[[], bool] | None,
    approved_action: Action | None = None,
    approval_denied: bool = False,
) -> AgentState:
    events: list[dict] = []

    def event(kind: str, data: dict) -> None:
        events.append(
            {
                "run_id": state.run_id,
                "seq": len(events),
                "kind": kind,
                "data": deepcopy(data),
            }
        )

    def stop(status: str, reason: str) -> None:
        state.status, state.stop_reason = status, reason

    if approved_action is not None:
        if approval_denied:
            call_id = f"{state.run_id}:{state.steps}"
            result = {
                "call_id": call_id,
                "ok": False,
                "error": {"code": "approval_denied", "retryable": False},
            }
            state.observations.append(deepcopy(result))
            state.history.append(
                StepRecord(
                    deepcopy(approved_action),
                    deepcopy(result),
                    datetime.now(timezone.utc).isoformat(),
                    0,
                )
            )
            event("approval_denied", {"call_id": call_id, "name": approved_action.name})
        else:
            _execute_action(state, approved_action, tools, event)

    repetitions: dict[str, int] = {}
    for step in state.history:
        sig = json.dumps(
            [
                step.action.name,
                step.action.arguments,
                {k: v for k, v in step.observation.items() if k != "call_id"},
            ],
            sort_keys=True,
        )
        repetitions[sig] = repetitions.get(sig, 0) + 1

    while state.steps < max_steps:
        if should_cancel is not None and should_cancel():
            stop("stopped", "cancelled")
            break
        if (
            max_total_tokens is not None
            and state.usage.total_tokens >= max_total_tokens
        ):
            stop("stopped", "token_budget")
            break
        state.status, state.stop_reason = "running", ""
        state.steps += 1
        try:
            raw_decision = deepcopy(model.decide(deepcopy(state)))
            decision = (
                raw_decision
                if isinstance(raw_decision, ModelDecision)
                else ModelDecision(raw_decision)
            )
            action, usage = decision.action, decision.usage
            if (
                not isinstance(usage, Usage)
                or min(usage.input_tokens, usage.output_tokens) < 0
            ):
                raise ValueError("usage must contain non-negative token counts")
            state.usage = Usage(
                state.usage.input_tokens + usage.input_tokens,
                state.usage.output_tokens + usage.output_tokens,
            )
            if not isinstance(action, Action) or action.kind not in {"tool", "finish"}:
                raise ValueError("model must return Action(tool|finish)")
            if action.kind == "finish":
                if not isinstance(action.answer, str) or not action.answer.strip():
                    raise ValueError("finish requires a non-empty answer")
                event("model_decision", {"action": "finish", "usage": asdict(usage)})
                state.answer = action.answer
                stop("completed", "model_finished")
                break
            if (
                not isinstance(action.name, str)
                or not action.name
                or not isinstance(action.arguments, dict)
            ):
                raise ValueError("tool requires name and object arguments")
            _validate_json(action.arguments)
            event(
                "model_decision",
                {
                    "action": "tool",
                    "name": action.name,
                    "arguments": action.arguments,
                    "usage": asdict(usage),
                },
            )
        except Exception as error:
            event("model_error", {"type": type(error).__name__})
            stop("failed", "invalid_model_output")
            break

        if max_total_tokens is not None and state.usage.total_tokens > max_total_tokens:
            stop("stopped", "token_budget")
            break
        tool = tools.get(action.name)
        if tool is not None and tool.requires_approval:
            decision_id = uuid4().hex
            state.pending_approval = {
                "decision_id": decision_id,
                "action": _action_data(action),
                "action_digest": _action_digest(action),
            }
            event(
                "approval_requested",
                {
                    "decision_id": decision_id,
                    "name": action.name,
                    "arguments": action.arguments,
                },
            )
            stop("waiting_for_input", "approval_required")
            break

        result = _execute_action(state, action, tools, event)
        signature = json.dumps(
            [
                action.name,
                action.arguments,
                {k: v for k, v in result.items() if k != "call_id"},
            ],
            sort_keys=True,
        )
        repetitions[signature] = repetitions.get(signature, 0) + 1
        if repetitions[signature] >= repeat_limit:
            stop("stopped", "no_progress")
            break
    else:
        stop("stopped", "max_steps")

    event(
        "run_finished",
        {
            "status": state.status,
            "reason": state.stop_reason,
            "steps": state.steps,
            "usage": asdict(state.usage),
        },
    )
    write_trace(trace_path, events)
    return state


def run_agent(
    model: Model,
    tools: dict[str, Tool],
    task: str,
    *,
    max_steps: int = 8,
    repeat_limit: int = 2,
    trace_path: str | None = None,
    max_total_tokens: int | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> AgentState:
    """Run a bounded synchronous loop. In-process handlers must be trusted."""
    if (
        max_steps < 1
        or repeat_limit < 1
        or (max_total_tokens is not None and max_total_tokens < 1)
    ):
        raise ValueError("budgets must be positive")
    state = AgentState(task=task, run_id=uuid4().hex)
    return _drive(
        model,
        tools,
        state,
        max_steps=max_steps,
        repeat_limit=repeat_limit,
        trace_path=trace_path,
        max_total_tokens=max_total_tokens,
        should_cancel=should_cancel,
    )


def resume_agent(
    model: Model,
    tools: dict[str, Tool],
    state: AgentState,
    approval: ApprovalDecision,
    *,
    max_steps: int = 8,
    repeat_limit: int = 2,
    trace_path: str | None = None,
    max_total_tokens: int | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> AgentState:
    """Resume exactly the action identified by a pending approval decision."""
    resumed = deepcopy(state)
    pending = resumed.pending_approval
    if resumed.status != "waiting_for_input" or not pending:
        raise ValueError("state is not waiting for approval")
    if approval.decision_id != pending["decision_id"]:
        raise ValueError("approval decision does not match pending action")
    action = Action(**pending["action"])
    if _action_digest(action) != pending["action_digest"]:
        raise ValueError("pending action changed after approval request")
    resumed.pending_approval = None
    return _drive(
        model,
        tools,
        resumed,
        max_steps=max_steps,
        repeat_limit=repeat_limit,
        trace_path=trace_path,
        max_total_tokens=max_total_tokens,
        should_cancel=should_cancel,
        approved_action=action,
        approval_denied=not approval.approved,
    )
