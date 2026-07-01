"""
Two-arm, isolated Opus-vs-Sonnet curation eval runner.

This is a self-contained agentic /curate loop (Anthropic Messages API tool-use),
parameterized ONLY by model id. It mirrors a normal /curate invocation: the agent
gets the AGENTS.md rules + a plain "curate this (Drug, Disease)" task, the same
PubMed / canonicalize / QC tools a Claude Code session would have, and writes one
path YAML per pair. The model is never told it is being compared or evaluated.

Why a new runner (not scripts/run_phase3_eval.py): that script is a SCORING layer
only — it assumes a human/Claude-Code session performs the curation interactively.
To compare two model ids head-to-head with zero shared context, the curation step
itself must be driven programmatically. This runner is that driver; it reuses the
exact tool-loop shape of scripts/quality/judge/backends.py:AnthropicBackend.

ISOLATION (enforced):
  * Each arm has its own output dir   experiments/opus_vs_sonnet/<arm>/outputs/
  * Each arm has its own PubMed cache  experiments/opus_vs_sonnet/<arm>/references_cache/
    (injected via DMDB_CACHE_DIR into every tool subprocess — see env override in
    scripts/pubmed_fetch.py / scripts/validate_references.py).
  * Each pair is a FRESH message history — no context bleeds between pairs.
  * The two arms never share outputs, cache, or conversation context.
  * Outputs land ONLY under experiments/ — never kb/paths/.

BLINDING:
  * The system prompt is the real AGENTS.md + the /curate workflow framing.
  * No "you are being tested / compared / evaluated" language anywhere.
  * Both arms get byte-identical framing, params, and retry budget. The ONLY
    difference between arms is --model.

USAGE:
  .venv-py310/bin/python experiments/opus_vs_sonnet/run_arm.py \
      --arm opus   --model claude-opus-4-8   --pairs P01,P02
  .venv-py310/bin/python experiments/opus_vs_sonnet/run_arm.py \
      --arm sonnet --model claude-sonnet-4-6 --pairs P01,P02

Omit --pairs to run all pairs in eval_pairs.yaml (the full sweep — do NOT do this
until the pilot cost is green-lit).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

EXP_DIR = Path(__file__).resolve().parent
REPO = EXP_DIR.parent.parent
PAIRS_FILE = EXP_DIR / "eval_pairs.yaml"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"

# Fixed, identical-for-both-arms settings. The ONLY per-arm difference is the model.
MAX_TOKENS = 8192
MAX_ITERS = 40          # agentic-loop turn cap (search/fetch/draft/canon/qc cycles)
RETRY_BUDGET = 3        # QC retries per AGENTS.md §5 (the agent self-manages within MAX_ITERS)

# Anthropic per-MTok pricing (claude-api skill, cached 2026-06):
#   opus-4-8   : $5 in  / $25 out ; sonnet-4-6 : $3 in / $15 out.
#   cache reads ~0.1x input, cache writes ~1.25x input.
PRICING = {
    "claude-opus-4-8":   {"in": 5.0,  "out": 25.0},
    "claude-opus-4-7":   {"in": 5.0,  "out": 25.0},
    "claude-sonnet-4-6": {"in": 3.0,  "out": 15.0},
}


def load_pairs() -> list[dict]:
    return yaml.safe_load(PAIRS_FILE.read_text()).get("pairs", [])


def py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


# ── tool subprocess plumbing ─────────────────────────────────────────────────
# Every script tool runs in a subprocess with DMDB_CACHE_DIR pointed at the arm's
# isolated cache, exactly like a real /curate session's restricted Bash surface.

def _run_script(arm_cache: Path, args: list[str], timeout: int = 240) -> str:
    env = os.environ.copy()
    env["DMDB_CACHE_DIR"] = str(arm_cache)
    try:
        p = subprocess.run([py(), *args], capture_output=True, text=True,
                           cwd=str(REPO), env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"ERROR: tool timed out after {timeout}s"
    out = (p.stdout or "") + (("\nSTDERR:\n" + p.stderr) if p.stderr else "")
    return out[:20000]  # cap tool output fed back to the model


def build_tools(arm_cache: Path, out_path: Path):
    """Return (tool_defs, registry). Mirrors the AGENTS.md §6 allowed surface."""
    sc = REPO / "scripts"

    def pubmed_search(a):
        return _run_script(arm_cache, [str(sc / "pubmed_fetch.py"), "search",
                                       a["query"], "--max", str(a.get("max", 20))])

    def pubmed_fetch(a):
        extra = []
        if a.get("fulltext"): extra.append("--fulltext")
        if a.get("max_fulltext") is not None:
            extra += ["--max-fulltext", str(a["max_fulltext"])]
        return _run_script(arm_cache, [str(sc / "pubmed_fetch.py"), "fetch",
                                       *a["pmids"], *extra])

    def pubmed_probe(a):
        return _run_script(arm_cache, [str(sc / "pubmed_fetch.py"), "probe",
                                       a["pmid"], "--json"])

    def read_cache(a):
        # Read a cached reference file (the verbatim-snippet source the agent must copy from).
        f = arm_cache / f"PMID_{a['pmid'].replace('PMID:','')}.md"
        if not f.exists():
            return f"ERROR: {f.name} not in cache. fetch it first."
        return f.read_text()[:20000]

    def write_path(a):
        out_path.write_text(a["yaml_content"])
        return f"Wrote {out_path.name} ({len(a['yaml_content'])} bytes)."

    def read_path(a):
        return out_path.read_text() if out_path.exists() else "ERROR: file not written yet."

    def canonicalize(a):
        return _run_script(arm_cache, [str(sc / "canonicalize_predicates.py"),
                                       "--write", str(out_path)])

    def run_qc(a):
        return _run_script(arm_cache, [str(sc / "qc.py"), "--profile", "ai_curated",
                                       str(out_path)])

    specs = [
        (pubmed_search, "pubmed_search",
         "Search PubMed for PMIDs matching a query. Returns matching PMIDs.",
         {"type": "object", "properties": {
             "query": {"type": "string"},
             "max": {"type": "integer", "description": "max results (default 20)"}},
          "required": ["query"]}),
        (pubmed_fetch, "pubmed_fetch",
         "Fetch abstract(s) for one or more PMIDs into the reference cache. Set fulltext=true to escalate to open-access full text.",
         {"type": "object", "properties": {
             "pmids": {"type": "array", "items": {"type": "string"}},
             "fulltext": {"type": "boolean"},
             "max_fulltext": {"type": "integer"}},
          "required": ["pmids"]}),
        (pubmed_probe, "pubmed_probe",
         "Check whether open-access full text is available for a PMID (no body download).",
         {"type": "object", "properties": {"pmid": {"type": "string"}},
          "required": ["pmid"]}),
        (read_cache, "read_reference",
         "Read the cached text (abstract or full text) for a PMID you have fetched. This is the ONLY acceptable source of verbatim snippets.",
         {"type": "object", "properties": {"pmid": {"type": "string"}},
          "required": ["pmid"]}),
        (write_path, "write_path_yaml",
         "Write the complete path YAML file (overwrites). Pass the full file contents.",
         {"type": "object", "properties": {"yaml_content": {"type": "string"}},
          "required": ["yaml_content"]}),
        (read_path, "read_path_yaml",
         "Read back the path YAML file you wrote.",
         {"type": "object", "properties": {}}),
        (canonicalize, "canonicalize_predicates",
         "Canonicalize predicate keys in the written path YAML (lowercase, strip biolink: prefix, underscores->spaces). Run before QC.",
         {"type": "object", "properties": {}}),
        (run_qc, "run_qc",
         "Run the 4-layer QC gate (ai_curated profile) on the written path YAML. Layer1 schema, Layer2 node ontology, Layer3 predicate, Layer4 verbatim reference.",
         {"type": "object", "properties": {}}),
    ]
    tool_defs = [{"name": n, "description": d, "input_schema": s} for (_fn, n, d, s) in specs]
    registry = {n: fn for (fn, n, _d, _s) in specs}
    return tool_defs, registry


# ── system prompt: real AGENTS.md framing, no eval/compare language ──────────

def build_system() -> str:
    agents = (REPO / "AGENTS.md").read_text()
    return (
        "You are the DrugMechDB curation agent. You curate a single new mechanistic "
        "path connecting a (Drug, Disease) pair, following the rules below exactly.\n\n"
        "You have these tools and no others (this mirrors the /curate tool surface):\n"
        "  pubmed_search, pubmed_fetch, pubmed_probe, read_reference,\n"
        "  write_path_yaml, read_path_yaml, canonicalize_predicates, run_qc.\n\n"
        "Workflow: resolve identifiers -> search PubMed and fetch+read the abstracts you "
        "will cite -> draft the path YAML and write it with write_path_yaml -> "
        "canonicalize_predicates -> run_qc -> iterate up to 3 times if QC fails. "
        "Every evidence snippet MUST be a verbatim substring of a cached reference you "
        "fetched (use read_reference to copy it) — never typed from memory, never paraphrased. "
        "Do NOT run the semantic critic step in this environment (critic.py is not available "
        "as a tool here); stop after QC passes or after 3 retries and report.\n\n"
        "When finished, send a final text message reporting: the QC layer-by-layer result, "
        "your retry count, the PMIDs cited, and any unresolved validation failures.\n\n"
        "=== AGENTS.md (authoritative rules) ===\n\n" + agents
    )


def build_task(pair: dict) -> str:
    # Plain /curate framing. Eval-mode override only specifies WHERE to write,
    # using the same wording shape as scripts/run_phase3_eval.py's prompt — no
    # "you are being evaluated/compared" language.
    return (
        f"Curate a new DrugMechDB mechanistic path for **{pair['drug']}** for "
        f"**{pair['disease']}**.\n\n"
        f"Known identifiers:\n"
        f"  drug_mesh    : {pair.get('drug_mesh','(resolve it)')}\n"
        f"  drugbank     : {pair.get('drugbank','(resolve it)')}\n"
        f"  disease_mesh : {pair['disease_mesh']}\n\n"
        f"Write your final YAML via the write_path_yaml tool. Set the graph `_id` to "
        f"`{pair['id']}_{(pair.get('drugbank') or 'DB:UNK').split(':')[-1]}_{pair['disease_mesh'].replace(':','_')}` "
        f"so it is a valid identifier. Follow AGENTS.md exactly; cite only verbatim snippets "
        f"from references you fetch. Iterate up to 3 times against run_qc."
    )


# ── the agentic loop (Anthropic Messages API tool-use) ───────────────────────

def run_pair(client, model: str, pair: dict, arm_cache: Path, out_path: Path) -> dict:
    tool_defs, registry = build_tools(arm_cache, out_path)
    # Prompt caching: the system prompt (AGENTS.md + framing) plus the fixed tool defs are
    # a large, byte-identical prefix reused on every turn of every pair. A cache_control
    # breakpoint on the system block caches tools+system together, so each reuse bills at
    # ~0.1x input instead of full price (5-min TTL stays warm across the tool-loop and even
    # across back-to-back pairs, since the prefix bytes are identical). Identical for both
    # arms — pure billing optimization, no effect on what either model sees.
    system = [{"type": "text", "text": build_system(), "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": build_task(pair)}]
    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    calls = []
    stopped = "final"
    final_text = ""   # ensure defined even if the API call raises before a final turn
    t0 = time.time()

    for i in range(MAX_ITERS):
        try:
            resp = client.messages.create(
                model=model, max_tokens=MAX_TOKENS, system=system,
                tools=tool_defs, messages=messages,
            )
        except Exception as e:
            stopped = f"error:{type(e).__name__}:{e}"
            break

        u = getattr(resp, "usage", None)
        if u is not None:
            for k in usage:
                usage[k] += getattr(u, k, 0) or 0

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if getattr(resp, "stop_reason", None) == "tool_use" and tool_uses:
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
                fn = registry.get(tu.name)
                try:
                    out = fn(tu.input or {}) if fn else f"ERROR: unknown tool {tu.name}"
                except Exception as e:
                    out = f"ERROR executing {tu.name}: {e}"
                calls.append({"name": tu.name, "input_keys": list((tu.input or {}).keys())})
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": str(out)})
            messages.append({"role": "user", "content": results})
            continue

        # final text turn
        final_text = "".join(getattr(b, "text", "") for b in resp.content
                             if getattr(b, "type", None) == "text")
        break
    else:
        stopped = "max_iters"
        final_text = ""

    wall = time.time() - t0
    pr = PRICING.get(model, {"in": 0, "out": 0})
    # billed input = uncached input + cache writes(1.25x) + cache reads(0.1x), all at input rate
    in_eff = (usage["input_tokens"]
              + usage["cache_creation_input_tokens"] * 1.25
              + usage["cache_read_input_tokens"] * 0.1)
    cost = (in_eff * pr["in"] + usage["output_tokens"] * pr["out"]) / 1_000_000

    return {
        "pair_id": pair["id"], "model": model, "stopped": stopped,
        "iters": i + 1, "wall_seconds": round(wall, 1),
        "usage": usage, "est_cost_usd": round(cost, 4),
        "n_tool_calls": len(calls),
        "tool_call_counts": _count(calls),
        "output_written": out_path.exists(),
        "final_text_tail": final_text[-1500:],
    }


def _count(calls):
    c = {}
    for x in calls:
        c[x["name"]] = c.get(x["name"], 0) + 1
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=["opus", "sonnet"])
    ap.add_argument("--model", required=True, help="claude-opus-4-8 | claude-sonnet-4-6")
    ap.add_argument("--pairs", default="", help="comma-separated pair ids; empty = all")
    args = ap.parse_args()

    try:
        import anthropic
    except ImportError:
        print("anthropic SDK not installed; pip install -e '.[judge]'", file=sys.stderr)
        return 2
    client = anthropic.Anthropic()

    arm_dir = EXP_DIR / args.arm
    out_dir = arm_dir / "outputs"
    arm_cache = arm_dir / "references_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    arm_cache.mkdir(parents=True, exist_ok=True)

    pairs = load_pairs()
    if args.pairs:
        want = set(args.pairs.split(","))
        pairs = [p for p in pairs if p["id"] in want]

    results = []
    for pair in pairs:
        out_path = out_dir / f"{pair['id']}.yaml"
        # Idempotent resume: skip pairs already curated in a prior (possibly crashed) run.
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"[{args.arm}/{args.model}] skip {pair['id']} (output exists)", flush=True)
            continue
        print(f"[{args.arm}/{args.model}] curating {pair['id']} "
              f"({pair['drug']} -> {pair['disease']}) ...", flush=True)
        r = run_pair(client, args.model, pair, arm_cache, out_path)
        results.append(r)
        print(f"  done: stopped={r['stopped']} iters={r['iters']} "
              f"wall={r['wall_seconds']}s cost=${r['est_cost_usd']} "
              f"written={r['output_written']}", flush=True)

    # Merge with any prior summary so a resumed run keeps earlier pairs' metrics.
    summary = arm_dir / "run_summary.json"
    prior = []
    if summary.exists():
        try:
            prior = json.loads(summary.read_text())
        except Exception:
            prior = []
    done_now = {r["pair_id"] for r in results}
    merged = [p for p in prior if p.get("pair_id") not in done_now] + results
    merged.sort(key=lambda r: r.get("pair_id", ""))
    results = merged
    summary.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {summary.relative_to(REPO)}")
    tot = sum(r["est_cost_usd"] for r in results)
    twall = sum(r["wall_seconds"] for r in results)
    print(f"Arm total: {len(results)} pairs, ${tot:.4f}, {twall:.0f}s wall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
