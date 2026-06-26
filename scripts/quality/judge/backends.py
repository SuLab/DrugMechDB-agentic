"""
Provider-agnostic agentic tool-loop for the judge.

A backend takes (system prompt, user message, tools) and runs a bounded
tool-use loop: the model may call grounding tools (executed locally), receive
results, and iterate until it emits a final text answer (the JSON verdict).

Three backends:
  - AnthropicBackend — Anthropic Messages API tool-use loop (different family
    than the curator when the curator is OpenAI; configurable).
  - OpenAIBackend    — OpenAI Chat Completions tool-call loop.
  - StubBackend      — deterministic, scripted; drives the *exact same* loop and
    tool execution with no network/keys, so every seam is testable offline.

Live backends import their SDK lazily, so importing this module never requires
anthropic/openai to be installed.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[[dict], str]


@dataclass
class LoopResult:
    final_text: str
    tool_calls: list = field(default_factory=list)   # [{name, input, result_preview}]
    iters: int = 0
    backend: str = ""
    model: str = ""
    usage: dict | None = None
    stopped: str = "final"   # final | max_iters | error


def _execute(tools: dict, name: str, args: dict, calls: list) -> str:
    tool = tools.get(name)
    if tool is None:
        result = f"ERROR: tool '{name}' is not available. Available: {sorted(tools)}."
    else:
        try:
            result = tool.fn(args or {})
        except Exception as e:  # tools should not raise, but never let one kill the loop
            result = f"ERROR executing {name}: {e}"
    if not isinstance(result, str):
        result = json.dumps(result, default=str)
    calls.append({"name": name, "input": args, "result_preview": result[:300]})
    return result


class Backend(ABC):
    name = ""

    @abstractmethod
    def run(self, system: str, user: str, tools: list[Tool], max_iters: int = 6) -> LoopResult:
        ...


# ── Anthropic ───────────────────────────────────────────────────────────────

class AnthropicBackend(Backend):
    name = "anthropic"

    def __init__(self, model: str, max_tokens: int = 4096):
        self.model = model
        self.max_tokens = max_tokens

    def run(self, system: str, user: str, tools: list[Tool], max_iters: int = 6) -> LoopResult:
        import anthropic  # lazy

        client = anthropic.Anthropic()
        registry = {t.name: t for t in tools}
        tool_defs = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
        messages = [{"role": "user", "content": user}]
        calls: list = []
        usage = {"input_tokens": 0, "output_tokens": 0}

        for i in range(max_iters):
            resp = client.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                system=system, tools=tool_defs, messages=messages,
            )
            u = getattr(resp, "usage", None)
            if u is not None:
                usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
                usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0

            text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
            tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]

            if getattr(resp, "stop_reason", None) == "tool_use" and tool_uses:
                # echo assistant turn back (reconstructed as dicts for SDK-version safety)
                asst = []
                for b in resp.content:
                    bt = getattr(b, "type", None)
                    if bt == "text":
                        asst.append({"type": "text", "text": b.text})
                    elif bt == "tool_use":
                        asst.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
                messages.append({"role": "assistant", "content": asst})
                results = []
                for tu in tool_uses:
                    out = _execute(registry, tu.name, tu.input, calls)
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
                messages.append({"role": "user", "content": results})
                continue

            return LoopResult(text, calls, i + 1, self.name, self.model, usage, "final")

        return LoopResult(text, calls, max_iters, self.name, self.model, usage, "max_iters")


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAIBackend(Backend):
    name = "openai"

    def __init__(self, model: str):
        self.model = model

    def run(self, system: str, user: str, tools: list[Tool], max_iters: int = 6) -> LoopResult:
        import openai  # lazy

        client = openai.OpenAI()
        registry = {t.name: t for t in tools}
        tool_defs = [{
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
        } for t in tools]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        calls: list = []

        for i in range(max_iters):
            resp = client.chat.completions.create(model=self.model, messages=messages, tools=tool_defs)
            msg = resp.choices[0].message
            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}
                    out = _execute(registry, tc.function.name, args, calls)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
                continue
            return LoopResult(msg.content or "", calls, i + 1, self.name, self.model, None, "final")

        return LoopResult("", calls, max_iters, self.name, self.model, None, "max_iters")


# ── Stub (deterministic, offline) ──────────────────────────────────────────────

class StubBackend(Backend):
    """Drives the real loop + tool execution with a scripted plan.

    `script` is a list of steps:
      {"call": [{"name": ..., "input": {...}}, ...]}  -> execute these tools, continue
      {"final": "<text>"}                             -> return this as the final answer
      "<text>"                                        -> shorthand for {"final": "<text>"}
    A callable `script(history)` may also be supplied for dynamic stubs.
    """
    name = "stub"

    def __init__(self, script, model: str = "stub-judge-1"):
        self.script = script
        self.model = model

    def run(self, system: str, user: str, tools: list[Tool], max_iters: int = 6) -> LoopResult:
        registry = {t.name: t for t in tools}
        calls: list = []
        steps = self.script(user) if callable(self.script) else list(self.script)
        for i, step in enumerate(steps[:max_iters]):
            if isinstance(step, str):
                step = {"final": step}
            if "final" in step:
                return LoopResult(step["final"], calls, i + 1, self.name, self.model, None, "final")
            for c in step.get("call", []):
                _execute(registry, c["name"], c.get("input", {}), calls)
        return LoopResult("", calls, len(steps), self.name, self.model, None, "max_iters")
