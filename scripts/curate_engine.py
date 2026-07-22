"""
scripts/curate_engine.py — the reusable, headless /curate engine (BUILD-ONLY).

This promotes the proven experiments/opus_vs_sonnet/run_arm.py agentic loop into a
production curation engine that a bulk campaign (scripts/campaign_runner.py's
AgenticBackend) drives one record at a time. It is the multi-turn Anthropic
Messages-API tool-use loop that a `/curate` session runs, made headless and
callable.

    passed_result = curate_one(work_item, model, cache_dir=<scratch>, out_path=<scratch>,
                               client=<mock in tests, real in a live run>)

── BUILD-ONLY / OFFLINE-TESTABLE ────────────────────────────────────────────────
This module NEVER curates on import and NEVER by default. Nothing here constructs a
real Anthropic client unless `curate_one(..., client=None)` is actually invoked in a
live run. Tests always pass a mock client, so no real Anthropic API call happens in
verification. The `main()` CLI is a dry-run that prints the real-run recipe and makes
no API call. A real run is an explicit, deliberate call the maintainer makes (see
`main()` docstring and the AgenticBackend in scripts/campaign_runner.py).

── THE CORPUS-READ GUARDRAIL (why "the agent seeing existing curations" is impossible)
The model is given an 8-tool allowlist and NOTHING else — no Bash, no general
filesystem read, no path into kb/paths. Enumerated:

    evidence_search / evidence_fetch / evidence_probe  — reach only external APIs via
        the source-agnostic evidence layer (scripts/evidence_fetch.py), writing ONLY
        into this call's isolated cache dir (DMDB_CACHE_DIR).
    read_reference   — reads ONLY a file inside this call's isolated cache dir; the
        target is derived from the reference CURIE via evidence_sources.common.
        cache_filename (which strips path separators) and is asserted to resolve
        directly inside the cache dir — a ref cannot escape it.
    write_path_yaml  — writes ONLY the single out_path (asserted NOT inside kb/paths).
    read_path_yaml   — reads ONLY that same out_path.
    canonicalize_predicates — rewrites predicates in that out_path.
    run_gate         — runs scripts/quality/gate.py on that out_path.

There is deliberately no tool that reads kb/paths, no shell, and no arbitrary file
read. So the curator physically cannot see any existing curation — it curates from
its own fetched evidence. The engine additionally REFUSES (ValueError) to run if
out_path or cache_dir resolves inside kb/paths.

── ISOLATION (safe for a bounded worker pool) ───────────────────────────────────
Every curate_one call is fully self-contained: a distinct out_path, a distinct
cache_dir exported as DMDB_CACHE_DIR to every tool subprocess, and a fresh message
history. There is NO shared mutable process state (no os.environ mutation) — the
cache dir travels per-subprocess via `env=`, so N workers in a ThreadPoolExecutor
never collide. Provenance is stamped per record (reusing campaign_runner.make_provenance)
and written to a `<out_path>.provenance.json` sidecar in the scratch dir.

Lifted from run_arm.py: the tool-loop shape, the retry/draft-forcing nudge, the
prompt-caching breakpoint on the system block. Changed: an 8-tool corpus-blind
allowlist (source-agnostic evidence layer), run_gate replaces run_qc, and thinking
blocks are preserved (run_arm dropped them; this passes them through so multi-turn
works for thinking-enabled models).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent              # scripts/
REPO = HERE.parent
sys.path.insert(0, str(HERE))                        # so `import campaign_runner` / `evidence_sources` resolve

AGENTS_MD = REPO / "AGENTS.md"
KB_PATHS = (REPO / "kb" / "paths").resolve()         # the corpus — the engine must NEVER write here
GATE = REPO / "scripts" / "quality" / "gate.py"
EVIDENCE_FETCH = REPO / "scripts" / "evidence_fetch.py"
CANON = REPO / "scripts" / "canonicalize_predicates.py"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"

DEFAULT_MODEL = "claude-opus-4-8"
MAX_TOKENS = 16384          # per-turn output ceiling (safe non-streaming; mirrors run_arm)
MAX_ITERS = 40              # agentic-loop turn cap (search/fetch/draft/canon/gate cycles)
# Draft-forcing nudges (model-neutral, lifted from run_arm): if the agent is STILL
# researching this late in the budget without a write, nudge it to draft. A no-op for
# models that draft early; only fires for a model that over-researches.
DRAFT_NUDGE_TURN_1 = 15
DRAFT_NUDGE_TURN_2 = 25
TOOL_TIMEOUT = 300
TOOL_OUTPUT_CAP = 20000     # cap tool output fed back to the model


# ── tool subprocess plumbing (per-call cache isolation via DMDB_CACHE_DIR) ─────

def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _run_script(cache_dir: Path, args: list[str], timeout: int = TOOL_TIMEOUT) -> tuple[int, str]:
    """Run a repo script tool in a subprocess whose DMDB_CACHE_DIR points at THIS
    call's isolated cache — never the committed references_cache/. The env is set
    on the subprocess only (never os.environ), so parallel workers never collide."""
    env = os.environ.copy()
    env["DMDB_CACHE_DIR"] = str(Path(cache_dir).resolve())
    try:
        p = subprocess.run([_py(), *args], capture_output=True, text=True,
                           cwd=str(REPO), env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"ERROR: tool timed out after {timeout}s"
    out = (p.stdout or "") + (("\nSTDERR:\n" + p.stderr) if p.stderr else "")
    return p.returncode, out[:TOOL_OUTPUT_CAP]


# ── path safety: the engine writes ONLY to an isolated scratch/output dir ──────

def _assert_safe_paths(out_path: Path, cache_dir: Path) -> None:
    """Hard guarantee: never write a curation (or its cache) inside the corpus."""
    op = Path(out_path).resolve()
    if op == KB_PATHS or KB_PATHS in op.parents:
        raise ValueError(f"curate_engine refuses to write inside the corpus (kb/paths): {op}")
    cp = Path(cache_dir).resolve()
    if cp == KB_PATHS or KB_PATHS in cp.parents:
        raise ValueError(f"curate_engine refuses to use a cache dir inside the corpus (kb/paths): {cp}")


# ── the 8-tool corpus-blind allowlist ─────────────────────────────────────────

def build_tools(cache_dir: Path, out_path: Path, *, offline: bool = False,
                gate_critic: bool = False, online_gate: bool = False):
    """Return (tool_defs, registry, state). The registry closes over the isolated
    cache_dir + out_path; `state` records the write flag and the latest gate result.
    This is the ENTIRE surface the model can act through — see the module docstring's
    corpus-read guardrail."""
    cache_dir = Path(cache_dir)
    out_path = Path(out_path)
    state: dict = {"wrote_yaml": False, "gate": None}

    def evidence_search(a: dict) -> str:
        code, out = _run_script(cache_dir, [str(EVIDENCE_FETCH), "search",
                                            a["source"], a["query"],
                                            "--max", str(a.get("max", 20))])
        return out

    def evidence_fetch(a: dict) -> str:
        extra: list[str] = []
        if a.get("fulltext"):
            extra.append("--fulltext")
        if a.get("max_fulltext") is not None:
            extra += ["--max-fulltext", str(a["max_fulltext"])]
        if offline:
            extra.append("--offline")
        code, out = _run_script(cache_dir, [str(EVIDENCE_FETCH), "fetch",
                                            *a["refs"], *extra])
        return out

    def evidence_probe(a: dict) -> str:
        code, out = _run_script(cache_dir, [str(EVIDENCE_FETCH), "probe",
                                            a["reference"], "--json"])
        return out

    def read_reference(a: dict) -> str:
        # Reads ONLY inside this call's isolated cache dir — the reference CURIE is
        # mapped to a bare filename (path separators stripped) and the resolved
        # target is asserted to sit directly in the cache dir. A ref cannot escape.
        from evidence_sources import common
        ref = a.get("reference") or a.get("ref") or a.get("pmid") or ""
        if not ref:
            return "ERROR: read_reference needs a `reference` CURIE."
        root = cache_dir.resolve()
        target = (root / common.cache_filename(ref)).resolve()
        if target.parent != root:
            return "ERROR: refusing to read outside the isolated cache."
        if not target.exists():
            return f"ERROR: {target.name} not in cache — fetch it first with evidence_fetch."
        return target.read_text(encoding="utf-8")[:TOOL_OUTPUT_CAP]

    def write_path_yaml(a: dict) -> str:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(a["yaml_content"], encoding="utf-8")
        state["wrote_yaml"] = True
        return f"Wrote {out_path.name} ({len(a['yaml_content'])} bytes)."

    def read_path_yaml(a: dict) -> str:
        return out_path.read_text(encoding="utf-8") if out_path.exists() \
            else "ERROR: file not written yet."

    def canonicalize_predicates(a: dict) -> str:
        code, out = _run_script(cache_dir, [str(CANON), "--write", str(out_path)])
        return out

    def run_gate(a: dict) -> str:
        # Calls scripts/quality/gate.py's run_gate (QC Layers 1-4 + structural + critic)
        # and returns the union feedback. Runs as a subprocess with the isolated
        # DMDB_CACHE_DIR so Layer 4 verbatim-checks against THIS call's cache only.
        # Default: offline (Layer 4 vs the isolated cache) + --no-critic (no LLM call).
        args = [str(GATE), str(out_path), "--json"]
        if not gate_critic:
            args.append("--no-critic")
        if online_gate:
            args.append("--online")
        code, out = _run_script(cache_dir, args)
        # The gate's JSON is on stdout; _run_script appends any stderr after a marker
        # (a critic run can be chatty on stderr). Parse the stdout portion for state.
        stdout_part = out.split("\nSTDERR:\n", 1)[0]
        parsed = None
        for candidate in (stdout_part, out):
            try:
                parsed = json.loads(candidate)
                break
            except Exception:
                continue
        state["gate"] = {"code": code, "feedback": parsed, "raw": out}
        return out

    specs = [
        (evidence_search, "evidence_search",
         "Search ONE evidence source for candidate reference CURIEs. Source is a prefix "
         "like PMID / chembl / clinicaltrials / bioRxiv / DrugBank.",
         {"type": "object", "properties": {
             "source": {"type": "string"},
             "query": {"type": "string"},
             "max": {"type": "integer", "description": "max results (default 20)"}},
          "required": ["source", "query"]}),
        (evidence_fetch, "evidence_fetch",
         "Fetch + cache reference(s) from ANY source into this session's isolated cache. "
         "Set fulltext=true to escalate to ephemeral open-access full text. This is the "
         "ONLY way source text enters the cache; you never author it.",
         {"type": "object", "properties": {
             "refs": {"type": "array", "items": {"type": "string"},
                      "description": "reference CURIEs, e.g. PMID:123 ChEMBL:CHEMBL25"},
             "fulltext": {"type": "boolean"},
             "max_fulltext": {"type": "integer"}},
          "required": ["refs"]}),
        (evidence_probe, "evidence_probe",
         "Check whether ephemeral full text is available for a reference (no body download).",
         {"type": "object", "properties": {"reference": {"type": "string"}},
          "required": ["reference"]}),
        (read_reference, "read_reference",
         "Read the cached text (abstract or full text) of a reference you FETCHED. This is "
         "the ONLY acceptable source of verbatim snippets. Reads only this session's cache.",
         {"type": "object", "properties": {"reference": {"type": "string"}},
          "required": ["reference"]}),
        (write_path_yaml, "write_path_yaml",
         "Write the complete path YAML file (overwrites). Pass the full file contents.",
         {"type": "object", "properties": {"yaml_content": {"type": "string"}},
          "required": ["yaml_content"]}),
        (read_path_yaml, "read_path_yaml",
         "Read back the path YAML file you wrote.",
         {"type": "object", "properties": {}}),
        (canonicalize_predicates, "canonicalize_predicates",
         "Canonicalize predicate keys in the written path YAML (lowercase, strip biolink: "
         "prefix, underscores->spaces). Run before run_gate.",
         {"type": "object", "properties": {}}),
        (run_gate, "run_gate",
         "Run the enforced curation gate (QC Layers 1-4 + structural checks + critic) on the "
         "written path YAML and return the union feedback. Fix every reported problem and "
         "re-run; iterate up to 3 times on a bounce.",
         {"type": "object", "properties": {}}),
    ]
    tool_defs = [{"name": n, "description": d, "input_schema": s} for (_fn, n, d, s) in specs]
    registry = {n: fn for (fn, n, _d, _s) in specs}
    return tool_defs, registry, state


# ── system + task prompt (real AGENTS.md framing; corpus-blindness stated) ─────

def build_system() -> str:
    agents = AGENTS_MD.read_text(encoding="utf-8")
    return (
        "You are the DrugMechDB curation agent, running headless. You curate a single new "
        "mechanistic path connecting one (Drug, Disease) pair, following AGENTS.md exactly.\n\n"
        "You have these tools and NO others (this is the entire /curate surface):\n"
        "  evidence_search, evidence_fetch, evidence_probe, read_reference,\n"
        "  write_path_yaml, read_path_yaml, canonicalize_predicates, run_gate.\n\n"
        "You CANNOT read the existing corpus (kb/paths), run shell commands, or read arbitrary "
        "files — by construction. Curate this path from scratch using ONLY evidence you fetch; "
        "never look for or imitate an existing curation.\n\n"
        "Workflow: resolve identifiers -> search sources and fetch+read the references you will "
        "cite -> draft the path YAML and write it with write_path_yaml -> canonicalize_predicates "
        "-> run_gate -> if it bounces, fix every reported problem and iterate (up to 3 times). "
        "Every evidence snippet MUST be a verbatim substring of a reference you fetched (use "
        "read_reference to copy it) — never typed from memory, never paraphrased.\n\n"
        "When finished, send a final text message reporting: the gate verdict, your retry count, "
        "the references cited, and any unresolved validation failures.\n\n"
        "=== AGENTS.md (authoritative rules) ===\n\n" + agents
    )


def build_task(item) -> str:
    drug = getattr(item, "drug", None) or "(unknown drug)"
    disease = getattr(item, "disease", None) or "(unknown disease)"
    item_id = getattr(item, "id", None) or "UNKNOWN"
    return (
        f"Curate a new DrugMechDB mechanistic path for **{drug}** for **{disease}**.\n\n"
        f"Known identifiers:\n"
        f"  drug_mesh    : {getattr(item, 'drug_mesh', None) or '(resolve it)'}\n"
        f"  drugbank     : {getattr(item, 'drugbank', None) or '(resolve it)'}\n"
        f"  disease_mesh : {getattr(item, 'disease_mesh', None) or '(resolve it)'}\n\n"
        f"Write your final YAML via write_path_yaml. Set the graph `_id` to `{item_id}`. "
        f"Follow AGENTS.md exactly; cite only verbatim snippets from references you fetch. "
        f"Iterate up to 3 times against run_gate."
    )


# ── result ─────────────────────────────────────────────────────────────────────

@dataclass
class CurationResult:
    item_id: str
    model: str
    out_path: str
    stopped: str = "final"
    iters: int = 0
    wrote_yaml: bool = False
    output_written: bool = False
    gate_passed: bool | None = None
    gate_verdict: str | None = None
    gate_feedback: dict | None = None
    tool_call_counts: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    final_text: str = ""
    provenance: dict | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.wrote_yaml and bool(self.gate_passed) and self.error is None

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["ok"] = self.ok
        return d


# ── multi-turn helpers ─────────────────────────────────────────────────────────

def _rebuild_assistant(content) -> list:
    """Rebuild the assistant turn for replay. Unlike run_arm (which dropped thinking),
    thinking / redacted_thinking blocks are PRESERVED UNCHANGED alongside tool_use, so
    multi-turn continuation works for thinking-enabled models (the API rejects a turn
    whose thinking blocks were modified or removed)."""
    asst: list = []
    for b in content:
        bt = getattr(b, "type", None)
        if bt == "text":
            asst.append({"type": "text", "text": b.text})
        elif bt == "thinking":
            blk = {"type": "thinking", "thinking": getattr(b, "thinking", "")}
            sig = getattr(b, "signature", None)
            if sig is not None:
                blk["signature"] = sig
            asst.append(blk)
        elif bt == "redacted_thinking":
            asst.append({"type": "redacted_thinking", "data": getattr(b, "data", "")})
        elif bt == "tool_use":
            asst.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return asst


def _count(calls: list[str]) -> dict:
    c: dict = {}
    for n in calls:
        c[n] = c.get(n, 0) + 1
    return c


def _build_real_client():
    """Construct a real Anthropic client. ONLY reached in a live run (client=None);
    tests always pass a mock, so this is never invoked during verification."""
    import anthropic
    return anthropic.Anthropic()


def _provenance(model: str, run_id: str | None) -> dict:
    # Reuse the campaign's single provenance definition (model / prompt_version /
    # git_sha / run_id / curated_at) rather than duplicating it here.
    from campaign_runner import make_provenance
    return make_provenance(model, run_id or uuid.uuid4().hex[:12])


# ── the engine ──────────────────────────────────────────────────────────────────

def curate_one(
    item,
    model: str = DEFAULT_MODEL,
    *,
    cache_dir,
    out_path,
    client=None,
    max_iters: int = MAX_ITERS,
    max_tokens: int = MAX_TOKENS,
    run_id: str | None = None,
    offline: bool = False,
    gate_critic: bool = False,
    online_gate: bool = False,
    thinking: bool = True,
    effort: str | None = "high",
    write_provenance: bool = True,
) -> CurationResult:
    """Run the multi-turn agentic /curate loop for one (drug, disease) work item.

    Writes ONLY to `out_path` (asserted outside kb/paths); every tool subprocess sees
    DMDB_CACHE_DIR == `cache_dir`. `client=None` constructs a real Anthropic client (a
    live run only) — tests pass a mock, so no real API call happens in verification.

    `offline`      — evidence_fetch adds --offline (cache-only; for reproducible runs).
    `gate_critic`  — let run_gate run the semantic critic (an LLM call). Default False
                     keeps the gate deterministic and call-free (the maintainer opts in).
    `online_gate`  — let the gate's Layer 4 fetch (default offline vs the isolated cache).
    """
    cache_dir = Path(cache_dir)
    out_path = Path(out_path)
    _assert_safe_paths(out_path, cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    item_id = getattr(item, "id", None) or "UNKNOWN"
    result = CurationResult(item_id=item_id, model=model, out_path=str(out_path))

    if client is None:
        client = _build_real_client()   # live run only; never in tests

    tool_defs, registry, state = build_tools(
        cache_dir, out_path, offline=offline, gate_critic=gate_critic, online_gate=online_gate)

    # Prompt caching: the system prompt (AGENTS.md + framing) + fixed tool defs are a
    # large, byte-identical prefix reused on every turn. A cache_control breakpoint on
    # the system block caches tools+system together — the big cost lever at corpus scale.
    system = [{"type": "text", "text": build_system(), "cache_control": {"type": "ephemeral"}}]
    messages: list = [{"role": "user", "content": build_task(item)}]

    create_kwargs: dict = {}
    if thinking:
        create_kwargs["thinking"] = {"type": "adaptive"}
    if effort:
        create_kwargs["output_config"] = {"effort": effort}

    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    calls: list[str] = []
    nudged: set = set()
    i = -1

    for i in range(max_iters):
        try:
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                tools=tool_defs, messages=messages, **create_kwargs,
            )
        except Exception as e:
            result.stopped = f"error:{type(e).__name__}"
            result.error = str(e)
            break

        u = getattr(resp, "usage", None)
        if u is not None:
            for k in usage:
                usage[k] += getattr(u, k, 0) or 0

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if getattr(resp, "stop_reason", None) == "tool_use" and tool_uses:
            messages.append({"role": "assistant", "content": _rebuild_assistant(resp.content)})
            results_blocks: list = []
            for tu in tool_uses:
                calls.append(tu.name)
                fn = registry.get(tu.name)
                try:
                    out = fn(tu.input or {}) if fn else f"ERROR: unknown tool {tu.name}"
                except Exception as e:
                    out = f"ERROR executing {tu.name}: {e}"
                results_blocks.append({"type": "tool_result", "tool_use_id": tu.id,
                                       "content": str(out)})

            # Draft-forcing nudge (lifted from run_arm): only if still researching late.
            turns_taken = i + 1
            if not state["wrote_yaml"]:
                if turns_taken >= DRAFT_NUDGE_TURN_2 and 2 not in nudged:
                    nudged.add(2)
                    results_blocks.append({"type": "text", "text": (
                        "STOP researching now — you have gathered enough references. THIS TURN, "
                        "draft your best-supported mechanistic path and call write_path_yaml, then "
                        "canonicalize_predicates and run_gate. Do not run any more searches or fetches.")})
                elif turns_taken >= DRAFT_NUDGE_TURN_1 and 1 not in nudged:
                    nudged.add(1)
                    results_blocks.append({"type": "text", "text": (
                        "You now have enough evidence for the edges in this mechanism. Move to "
                        "drafting: write the complete path YAML and call write_path_yaml, then "
                        "canonicalize_predicates and run_gate, iterating up to 3 times if it bounces.")})
            messages.append({"role": "user", "content": results_blocks})
            continue

        # final turn (also covers stop_reason 'end_turn' / 'refusal')
        result.stopped = getattr(resp, "stop_reason", "final") or "final"
        result.final_text = "".join(getattr(b, "text", "") for b in resp.content
                                    if getattr(b, "type", None) == "text")
        break
    else:
        result.stopped = "max_iters"

    result.iters = i + 1
    result.wrote_yaml = state["wrote_yaml"]
    result.output_written = out_path.exists()
    result.tool_call_counts = _count(calls)
    result.usage = usage

    g = state.get("gate")
    if g and isinstance(g.get("feedback"), dict):
        fb = g["feedback"]
        result.gate_feedback = fb
        result.gate_verdict = fb.get("verdict")
        result.gate_passed = bool(fb.get("passed"))
    elif g is not None:
        # gate ran but its JSON did not parse (crash / exit 2) — treat as not passed
        result.gate_passed = (g.get("code") == 0)

    result.provenance = _provenance(model, run_id)
    if write_provenance:
        try:
            sidecar = out_path.with_suffix(out_path.suffix + ".provenance.json")
            sidecar.write_text(json.dumps(result.provenance, indent=2), encoding="utf-8")
        except Exception:
            pass
    return result


# ── CLI: dry-run only — NEVER curates on its own ─────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """BUILD-ONLY dry run. This prints the real-run recipe and makes NO API call.

    A real curation is an explicit, deliberate call the maintainer makes — never this
    CLI, never on import, never automatic. The two supported live entrypoints are:

      # one record (programmatic):
      from scripts import curate_engine                      # (with scripts/ importable)
      from campaign_runner import WorkItem
      r = curate_engine.curate_one(
              WorkItem(id="DB00945_MESH_D009203_1", drug="Aspirin",
                       disease="Myocardial infarction", disease_mesh="MESH:D009203"),
              model="claude-opus-4-8",
              cache_dir="_recuration_output/cache/DB00945_MESH_D009203_1",
              out_path="_recuration_output/paths/DB00945_MESH_D009203_1.yaml",
              client=None)                                   # None => constructs anthropic.Anthropic()

      # the whole corpus (bounded worker pool):
      from campaign_runner import CampaignRunner, AgenticBackend
      CampaignRunner().run(AgenticBackend(model="claude-opus-4-8", workers=4))
    """
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args(argv)
    print("curate_engine: BUILD-ONLY. This CLI performs NO curation and makes NO API call.")
    print("A live run is an explicit CampaignRunner.run(AgenticBackend(...)) or curate_one(...)")
    print("call the maintainer makes deliberately — see main()'s docstring for the exact recipe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
