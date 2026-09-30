"""LLM providers and models, behind one small abstraction.

The assistant talks to a :class:`LLMProvider` by name (``assistant.provider``)
and asks it for a reply from one of its :class:`LLMModel` s (``assistant.model``).
Both are chosen in config/retplan.yaml and can be switched by the administrator
on the Assistant settings page; nothing else in RetPlan knows which vendor is
behind them.

Messages and tools are in one neutral shape:

- a message is ``{"role": "user" | "assistant", "text": str,
  "tool_calls": [ToolCall], "tool_results": [ToolResult]}``;
- a tool is ``{"name", "description", "schema"}`` (a JSON Schema for its input);
- a reply is :class:`LLMReply` - text, the tools the model asked to call, why it
  stopped, and the tokens used.

Each provider translates to and from its own API. Two ship:

- ``anthropic`` - Claude, through the Messages API over plain HTTPS (no SDK needed);
- ``fake``      - no model at all. Its ``fake-null`` model does nothing: it answers
  with a fixed note, calls no tools and uses no tokens - for trying the assistant's
  pages, or running RetPlan with the assistant switched on but offline. A fake
  provider can also be given a script of replies, which the tests use.

To add a provider: subclass :class:`LLMProvider`, list its models, implement
:meth:`LLMProvider.reply`, and :func:`register` it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# the neutral shapes
# --------------------------------------------------------------------------- #
@dataclass
class LLMModel:
    id: str
    label: str
    notes: str = ""
    tools: bool = True                 # can it call tools?
    max_output: int = 8192


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    id: str
    content: str                        # JSON text
    is_error: bool = False


@dataclass
class LLMReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop: str = "end"                   # end | tool_use | max_tokens | error
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""


class ProviderError(Exception):
    """The provider could not be reached, refused, or answered nonsense."""


class LLMProvider:
    key = "base"
    label = "Base"
    needs_key = True
    blurb = ""

    def models(self) -> list[LLMModel]:
        return []

    def model(self, model_id: str) -> LLMModel:
        """A known model, or one typed in configuration that the list does not have."""
        for m in self.models():
            if m.id == model_id:
                return m
        return LLMModel(model_id, model_id, "Not in RetPlan's list - taken as given.")

    def available(self, settings) -> tuple[bool, str]:
        if self.needs_key and not settings.api_key:
            return False, "No API key: set ANTHROPIC_API_KEY, or assistant.api_key in config/retplan.local.yaml."
        return True, "Ready."

    def reply(self, model: str, system: str, messages: list[dict], tools: list[dict],
              settings) -> LLMReply:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Anthropic (Claude)
# --------------------------------------------------------------------------- #
class AnthropicProvider(LLMProvider):
    key = "anthropic"
    label = "Anthropic (Claude)"
    blurb = "Claude models through the Anthropic Messages API."
    API_VERSION = "2023-06-01"
    DEFAULT_URL = "https://api.anthropic.com"

    def __init__(self, opener=None):
        self._open = opener or urllib.request.urlopen

    def models(self) -> list[LLMModel]:
        return [
            LLMModel("claude-opus-5-5", "Claude Opus 5.5",
                     "The most capable: explaining a strategy, writing the report.", max_output=32000),
            LLMModel("claude-sonnet-5-5", "Claude Sonnet 5.5",
                     "Fast and capable: conversation, what-ifs, reviews.", max_output=16000),
            LLMModel("claude-haiku-4-5-20251001", "Claude Haiku 4.5",
                     "The quickest and cheapest.", max_output=8192),
        ]

    @staticmethod
    def _to_api(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if m["role"] == "user":
                blocks = [{"type": "tool_result", "tool_use_id": r.id, "content": r.content,
                           **({"is_error": True} if r.is_error else {})}
                          for r in m.get("tool_results") or []]
                if m.get("text"):
                    blocks.append({"type": "text", "text": m["text"]})
                out.append({"role": "user", "content": blocks})
            else:
                blocks = [{"type": "text", "text": m["text"]}] if m.get("text") else []
                blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input}
                           for c in m.get("tool_calls") or []]
                out.append({"role": "assistant", "content": blocks})
        return out

    def reply(self, model, system, messages, tools, settings) -> LLMReply:
        body = {"model": model, "max_tokens": settings.max_tokens, "system": system,
                "temperature": settings.temperature, "messages": self._to_api(messages)}
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"],
                              "input_schema": t["schema"]} for t in tools]
        url = (settings.base_url or self.DEFAULT_URL).rstrip("/") + "/v1/messages"
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"x-api-key": settings.api_key,
                                              "anthropic-version": self.API_VERSION,
                                              "content-type": "application/json"})
        try:
            with self._open(req, timeout=settings.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:  # noqa: BLE001
                detail = ""
            raise ProviderError(f"Anthropic answered {exc.code}{': ' + detail if detail else ''}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ProviderError(f"Anthropic could not be reached: {exc}") from exc
        if data.get("type") == "error":
            raise ProviderError(data.get("error", {}).get("message", "an error"))
        texts, calls = [], []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(block.get("id", ""), block.get("name", ""),
                                      block.get("input") or {}))
        usage = data.get("usage") or {}
        return LLMReply(text="\n".join(t for t in texts if t).strip(), tool_calls=calls,
                        stop={"tool_use": "tool_use", "max_tokens": "max_tokens"}.get(
                            data.get("stop_reason"), "end"),
                        tokens_in=int(usage.get("input_tokens") or 0),
                        tokens_out=int(usage.get("output_tokens") or 0),
                        model=data.get("model", model))


# --------------------------------------------------------------------------- #
# Fake: no model at all
# --------------------------------------------------------------------------- #
FAKE_NOTE = ("This is RetPlan's fake assistant. It is not connected to any language model, so it "
             "does nothing: it runs no tools and has no answer. To talk to a real model, choose "
             "another provider on the Assistant settings page, or set assistant.provider in "
             "config/retplan.yaml.")


class FakeProvider(LLMProvider):
    key = "fake"
    label = "Fake (no model)"
    needs_key = False
    blurb = "Does nothing - for trying the assistant's pages without a model or a key."

    def __init__(self, script: list | None = None):
        # a script of LLMReply (or callables returning one), for the tests
        self.script = list(script or [])
        self.seen: list[dict] = []          # every request, for the tests to inspect

    def models(self) -> list[LLMModel]:
        return [LLMModel("fake-null", "Fake - does nothing",
                         "Answers with a fixed note; calls no tools; uses no tokens.", tools=False),
                LLMModel("fake-tools", "Fake - with tools, for tests",
                         "Also does nothing, but is offered the tools, so a scripted fake can "
                         "exercise the whole loop.")]

    def reply(self, model, system, messages, tools, settings) -> LLMReply:
        self.seen.append(dict(model=model, system=system, messages=messages, tools=tools))
        if self.script:
            step = self.script.pop(0)
            return step(messages, tools) if callable(step) else step
        return LLMReply(text=FAKE_NOTE, model=model)


# --------------------------------------------------------------------------- #
# the registry
# --------------------------------------------------------------------------- #
_REGISTRY: dict[str, LLMProvider] = {}


def register(provider: LLMProvider) -> None:
    _REGISTRY[provider.key] = provider


def providers() -> list[LLMProvider]:
    return list(_REGISTRY.values())


def get(key: str) -> LLMProvider | None:
    return _REGISTRY.get(key)


register(AnthropicProvider())
register(FakeProvider())
