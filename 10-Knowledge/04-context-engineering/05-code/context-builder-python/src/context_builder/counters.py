from dataclasses import dataclass
from typing import Any, Callable


def byte_tokens(text: str) -> int:
    """Teaching counter only: one UTF-8 byte is treated as one token."""
    return len(text.encode("utf-8"))


@dataclass(frozen=True)
class TokenizerCounter:
    """Adapt a provider tokenizer's encode(text) function without a dependency."""

    encode: Callable[[str], list[Any]]

    def __call__(self, text: str) -> int:
        return len(self.encode(text))


@dataclass(frozen=True)
class ChatTemplateCounter:
    """Count a provider-rendered chat request, including tools and role markers."""

    render: Callable[[list[dict], list[dict]], str]
    counter: Callable[[str], int]

    def count_request(self, messages: list[dict], tools: list[dict]) -> int:
        return self.counter(self.render(messages, tools))
