"""Optional OpenAI-compatible Chat Completions adapter using the standard library."""

import json
from typing import Any, Callable
from urllib.request import Request, urlopen

from .models import Action, AgentState, ModelDecision, Usage
from .tools import Tool

Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


class ModelRefusalError(ValueError):
    pass


class TruncatedResponseError(ValueError):
    pass


def urllib_transport(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    request = Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    with urlopen(request, timeout=timeout) as response:  # nosec: caller controls the endpoint
        return json.loads(response.read().decode("utf-8"))


class OpenAICompatibleAdapter:
    """Convert one complete Chat Completions response into the internal action contract."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        tools: dict[str, Tool],
        system_prompt: str = "You are a careful tool-using agent.",
        timeout_seconds: float = 60,
        transport: Transport = urllib_transport,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.tools = tools
        self.system_prompt = system_prompt
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _messages(self, state: AgentState) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": state.task},
        ]
        for index, step in enumerate(state.history, start=1):
            call_id = step.observation.get("call_id", f"call-{index}")
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": step.action.name,
                                "arguments": json.dumps(
                                    step.action.arguments, ensure_ascii=False
                                ),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(step.observation, ensure_ascii=False),
                }
            )
        return messages

    def decide(self, state: AgentState) -> ModelDecision:
        tool_specs = []
        for name, tool in self.tools.items():
            if not tool.allowed:
                continue
            tool_specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.description,
                        "parameters": tool.parameters
                        or {"type": "object", "properties": {}},
                    },
                }
            )
        payload = {
            "model": self.model,
            "messages": self._messages(state),
            "tools": tool_specs,
        }
        response = self.transport(
            self.url,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            payload,
            self.timeout_seconds,
        )
        choices = response.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("response must contain exactly one choice")
        choice = choices[0]
        if choice.get("finish_reason") in {"length", "content_filter"}:
            raise TruncatedResponseError("response did not finish normally")
        message = choice.get("message", {})
        if message.get("refusal"):
            raise ModelRefusalError("model refused the request")
        calls = message.get("tool_calls") or []
        if len(calls) > 1:
            raise ValueError(
                "parallel tool calls are not supported by this teaching loop"
            )
        if calls:
            function = calls[0].get("function", {})
            arguments = json.loads(function.get("arguments", ""))
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
            action = Action("tool", str(function.get("name", "")), arguments)
        else:
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("response contains neither a tool call nor final text")
            action = Action("finish", answer=content)
        raw_usage = response.get("usage") or {}
        usage = Usage(
            int(raw_usage.get("prompt_tokens", 0)),
            int(raw_usage.get("completion_tokens", 0)),
        )
        return ModelDecision(action, usage)
