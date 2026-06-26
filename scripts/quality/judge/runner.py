"""
Judge runner — drives a judge prompt through a backend's tool-loop and parses the
verdict. Shared by the edge-evidence and path-coherence judges.

Responsibilities:
  - load the SYSTEM PROMPT section from a prompt .md spec,
  - serialize the structured input the prompt expects,
  - run the backend loop with the grounding tools,
  - robustly extract the JSON verdict from the model's final text,
  - cache verdicts on disk (keyed by system+input+model) for reproducibility/cost.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .backends import Backend, Tool

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
VERDICT_CACHE = REPO / "quality_cache" / "verdicts"


def load_system_prompt(prompt_path: Path) -> str:
    """Return the text under the '## SYSTEM PROMPT' heading of a prompt spec."""
    text = Path(prompt_path).read_text(encoding="utf-8")
    m = re.search(r"##\s*SYSTEM PROMPT\s*\n", text)
    body = text[m.end():] if m else text
    # Drop a leading horizontal rule if present.
    return body.lstrip().lstrip("-").lstrip()


def extract_json(text: str):
    """Extract the first balanced JSON object/array from model text.

    Tolerates ```json fences and surrounding prose. Returns the parsed value, or a
    dict with _parse_error when nothing parseable is found.
    """
    if not text:
        return {"_parse_error": "empty model output", "_raw": text}
    # Prefer a fenced block if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)

    for cand in candidates:
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cand.find(opener)
            if start == -1:
                continue
            depth, in_str, esc = 0, False, False
            for i in range(start, len(cand)):
                ch = cand[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        blob = cand[start:i + 1]
                        try:
                            return json.loads(blob)
                        except Exception:
                            break  # try next candidate/opener
    return {"_parse_error": "no parseable JSON in model output", "_raw": text[:2000]}


def _cache_key(system: str, user: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(system.encode()); h.update(b"\x00"); h.update(user.encode()); h.update(b"\x00"); h.update(model.encode())
    return h.hexdigest()[:24]


def run_judge(
    prompt_path: Path,
    user_input: dict,
    tools: list[Tool],
    backend: Backend,
    *,
    max_iters: int = 6,
    use_cache: bool = True,
) -> dict:
    system = load_system_prompt(prompt_path)
    user = json.dumps(user_input, indent=2, default=str)
    model = getattr(backend, "model", backend.name)

    key = _cache_key(system, user, model)
    cache_file = VERDICT_CACHE / f"{key}.json"
    # The stub backend is for tests — never serve/poison the on-disk cache with it.
    if use_cache and backend.name != "stub" and cache_file.exists():
        try:
            bundle = json.loads(cache_file.read_text())
            bundle["cached"] = True
            return bundle
        except Exception:
            pass

    result = backend.run(system, user, tools, max_iters=max_iters)
    bundle = {
        "verdict": extract_json(result.final_text),
        "raw": result.final_text,
        "tool_calls": result.tool_calls,
        "backend": result.backend,
        "model": result.model,
        "iters": result.iters,
        "usage": result.usage,
        "stopped": result.stopped,
        "cached": False,
    }
    if use_cache and backend.name != "stub":
        VERDICT_CACHE.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(bundle, indent=2, default=str))
    return bundle
