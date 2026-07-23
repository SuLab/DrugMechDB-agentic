#!/usr/bin/env python3
"""
Blinded LLM-judge harness — run the semantic judge over a pilot's curated paths.

WHAT THIS IS
    A thin orchestration layer over the existing DrugMechDB semantic judge
    (scripts/quality/judge/). It takes a directory of curated path YAMLs — the
    pilot output — runs the edge-evidence judge (Layer 5) and the path-coherence
    judge (Layers 6/7) over each path, and writes a results table (JSON + a
    readable Markdown). It does NOT reimplement judging: it imports and calls
    `judge_edges` / `judge_path` and reuses `quality_profile.edge_faithfulness`
    for the per-path edge aggregate.

BLINDING (framework §7)
    The judge is never told which model produced which path. Two guarantees:
      1. The judge input is built by the existing `build_edge_inputs` /
         `build_path_input` functions, which pass only path *content*
         (nodes / predicates / evidence, and drug/disease/mesh) — never the
         record `_id`, the source directory, or a model tag.
      2. Paths from all arms are pooled and shuffled under a fixed seed and given
         anonymous blind ids (B001, B002, ...). The per-path `results` block is
         blind (keyed by blind_id only). The arm/source is recorded separately in
         a `reveal_key`, joined back only to compute the post-scoring aggregate.

INDEPENDENCE (framework §6c)
    Verification is trustworthy because of *grounding*, not IQ, and a judge in a
    DIFFERENT model family than the curator breaks the shared-prior problem at
    near-zero cost. The pilot is Claude-curated, so the judge defaults to a
    cross-family model (OpenAI) when its key is present; it falls back to
    Anthropic Opus with an explicit reduced-independence note otherwise. Judge
    provider/model are CLI args (`--judge-provider`, `--judge-model`).

MODES (no real API call by default or in tests)
    (default)  DRY-RUN / plan — discover + blind + resolve legacy paths, print the
               plan and the judge that WOULD be used. No backend, no API.
    --run      REAL judging — builds a live backend (needs an API key). This is the
               only mode that calls an LLM API.
    --stub     OFFLINE self-test — runs the full judge orchestration with the
               deterministic StubBackend from judge/backends.py. Zero API even when
               a key is present. Used by tests and by --self-check below.

USAGE
    # Plan only (no API):
    python scripts/run_blinded_judge.py experiments/pilot/opus experiments/pilot/sonnet \
        --eval-pairs experiments/pilot/eval_pairs.yaml --out-dir experiments/pilot/blinded

    # Offline orchestration check (no API):
    python scripts/run_blinded_judge.py opus=<dir> sonnet=<dir> --stub --out-dir /tmp/bj

    # Real blinded judge pass (needs OPENAI_API_KEY, cross-family default):
    python scripts/run_blinded_judge.py <dir> --run --out-dir experiments/pilot/blinded

Each positional INPUT is either a directory (arm label = its basename) or
`LABEL=DIR` to name the arm explicitly. Legacy/gold comparison is optional: pass
`--eval-pairs` (a file with a `pairs:` list of {id, legacy_path_id}) and
`--kb-dir` (read-only; default kb/paths) and the harness loads the matching legacy
path as the judge's `gold_path`, so the path judge emits `gold_comparison`.

Exit: 0 ok · 2 setup error (no inputs / --run without a key).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent            # scripts/
REPO = HERE.parent
sys.path.insert(0, str(HERE / "quality"))         # so quality_profile / judge.* / structural_quality import

import quality_profile as qp                        # noqa: E402  (edge_faithfulness, make_backend)
import structural_quality                           # noqa: E402
from judge.backends import Backend, StubBackend     # noqa: E402
from judge.edge_evidence_judge import judge_edges   # noqa: E402
from judge.path_coherence_judge import judge_path   # noqa: E402

LEX = qp.LEX
_VERDICTS = ("accept", "revise", "reject", "abstain")
_GOLD_CLASSES = ("reproduces", "agent_more_complete", "agent_simpler_but_valid", "disagree")


# ── input discovery ───────────────────────────────────────────────────────────

def discover_inputs(specs: list[str]) -> list[dict]:
    """Turn positional specs into a list of {arm, file} records (sorted per arm).

    A spec is either a directory (arm = basename) or `LABEL=DIR`.
    """
    items: list[dict] = []
    for spec in specs:
        if "=" in spec and not Path(spec).exists():
            label, _, dpath = spec.partition("=")
        elif "=" in spec and Path(spec.split("=", 1)[1]).is_dir():
            label, _, dpath = spec.partition("=")
        else:
            label, dpath = None, spec
        d = Path(dpath)
        if not d.is_dir():
            raise SystemExit(f"input '{spec}' is not a directory")
        arm = label or d.name
        files = sorted(f for f in d.glob("*.yaml") if f.name != "_index.yaml")
        for f in files:
            items.append({"arm": arm, "file": f})
    return items


def assign_blind_ids(items: list[dict], seed: int) -> list[dict]:
    """Pool + shuffle (seeded) + assign anonymous blind ids. Returns new records."""
    order = list(items)
    random.Random(seed).shuffle(order)
    width = max(3, len(str(len(order))))
    blinded = []
    for i, rec in enumerate(order, start=1):
        blinded.append({"blind_id": f"B{str(i).zfill(width)}", "arm": rec["arm"], "file": rec["file"]})
    return blinded


# ── legacy / gold-path resolution (READ-ONLY; never writes kb/) ────────────────

def load_eval_pairs(path: str | None) -> dict:
    """Map pair-id -> legacy_path_id from an eval_pairs.yaml (`pairs:` list)."""
    if not path:
        return {}
    data = yaml.safe_load(Path(path).read_text()) or {}
    out = {}
    for p in data.get("pairs", []) or []:
        pid = p.get("id")
        if pid and p.get("legacy_path_id"):
            out[str(pid)] = str(p["legacy_path_id"])
    return out


def _pair_ids(file: Path, doc: dict):
    """Candidate pair ids for a curated file: its stem, then the leading token of _id."""
    yield file.stem
    _id = (doc.get("graph") or {}).get("_id")
    if _id:
        yield str(_id).split("_")[0]


def _compact_path(doc: dict) -> dict:
    """A small, content-only view of a path for the judge's gold_path slot."""
    nodes = {}
    for n in doc.get("nodes") or []:
        if isinstance(n, dict) and n.get("id"):
            nodes[n["id"]] = {"id": n["id"], "name": n.get("name"), "label": n.get("label")}
    path = []
    for e in doc.get("links") or []:
        s = nodes.get(e.get("source"), {}).get("name") or e.get("source")
        t = nodes.get(e.get("target"), {}).get("name") or e.get("target")
        path.append(f"{s} --{e.get('key')}--> {t}")
    g = doc.get("graph") or {}
    return {"graph": {"drug": g.get("drug"), "disease": g.get("disease")},
            "path": path, "nodes": list(nodes.values())}


def resolve_legacy(file: Path, doc: dict, pair_map: dict, kb_dir: Path):
    """Return (legacy_path_id, gold_path_compact) or (None, None). Read-only.

    Resolution order: (1) an explicit `graph.legacy_path_id` on the record; (2) the
    eval-pairs map (pair id -> legacy id), matched by filename stem or the leading
    token of `graph._id`; (3) the re-curation case — the record's own id (filename
    stem or full `graph._id`) already names an existing record under `kb_dir`.
    """
    g = doc.get("graph") or {}
    _id = g.get("_id")
    legacy_id = g.get("legacy_path_id")
    if not legacy_id:
        for pid in _pair_ids(file, doc):
            if pid in pair_map:
                legacy_id = pair_map[pid]
                break
    if not legacy_id:  # re-curation of an existing record: its id names a kb file
        for cand in (file.stem, _id):
            if cand and (kb_dir / f"{cand}.yaml").exists():
                legacy_id = str(cand)
                break
    if not legacy_id:
        return None, None
    gold_file = kb_dir / f"{legacy_id}.yaml"
    if not gold_file.exists():
        return str(legacy_id), None
    try:
        gold_doc = yaml.safe_load(gold_file.read_text())
        return str(legacy_id), _compact_path(gold_doc)
    except Exception:
        return str(legacy_id), None


# ── small verdict extractors (robust to shape drift) ───────────────────────────

def _verdict_str(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip().lower() or None
    if isinstance(v, dict):
        for k in ("verdict", "classification", "relationship", "label", "result"):
            if v.get(k):
                return str(v[k]).strip().lower()
    return None


def _present(v) -> bool:
    if isinstance(v, dict):
        return bool(v.get("present"))
    return bool(v)


# ── judge backend selection ────────────────────────────────────────────────────

def resolve_judge(provider: str, model: str | None, curator_family: str) -> tuple[str, str | None, str, bool]:
    """Return (resolved_provider, resolved_model, note, key_available).

    provider ∈ {auto, openai, anthropic}. `auto` prefers a DIFFERENT family than
    the curator (framework §6c): OpenAI when its key exists, else Anthropic Opus
    with a reduced-independence note.
    """
    has_o = bool(os.environ.get("OPENAI_API_KEY"))
    has_a = bool(os.environ.get("ANTHROPIC_API_KEY"))
    curator = (curator_family or "anthropic").lower()

    if provider == "auto":
        provider = "openai" if has_o else ("anthropic" if has_a else "openai")

    if provider == "openai":
        m = model or "gpt-5"
        cross = curator != "openai"
        note = (f"judge=openai:{m} — {'cross-family vs ' + curator + ' curator (framework §6c)' if cross else 'SAME family as curator (reduced independence)'}")
        return "openai", m, note, has_o
    # anthropic
    m = model or "claude-opus-4-8"
    same = curator == "anthropic"
    note = (f"judge=anthropic:{m} — "
            + ("SAME family as the Claude curator: independence rests on grounding + cite-or-abstain, not model diversity; "
               "prefer OpenAI (set OPENAI_API_KEY) for a cross-family check" if same
               else f"cross-family vs {curator} curator"))
    return "anthropic", m, note, has_a


def build_backend(provider: str, model: str | None) -> tuple[Backend | None, str]:
    """Construct a live backend via quality_profile.make_backend (reuses its key
    checks), applying the CLI model override through DMDB_JUDGE_MODEL."""
    if model:
        os.environ["DMDB_JUDGE_MODEL"] = model
    return qp.make_backend(provider)


# ── the stub judge (offline, deterministic — used by --stub and by tests) ──────

def stub_responder(user: str):
    """A deterministic scripted judge that returns valid verdict JSON for both the
    edge and path judges, with mild hash-driven variety so the results table is
    exercised. NEVER calls a tool (returns only `final`), so it touches no network."""
    inp = json.loads(user)
    if "structural_report" in inp or "edge_verdicts" in inp:  # path-coherence judge
        drug = (inp.get("graph") or {}).get("drug") or ""
        h = int(hashlib.sha256(drug.encode()).hexdigest(), 16)
        overall = ["accept", "accept", "revise", "reject"][h % 4]
        gold = inp.get("gold_path")
        gc = _GOLD_CLASSES[h % 4] if gold else None
        out = {
            "mechanism_is_accepted": {"verdict": "yes", "basis": "stub", "confidence": "high"},
            "net_effect_correct": {"verdict": "yes", "basis": "stub"},
            "missing_step": {"present": overall == "revise"},
            "wrong_intermediate": {"present": False},
            "is_primary_moa": {"verdict": "yes"},
            "no_shortcut_edge": {"present": False, "offending_edge": None},
            "gold_comparison": {"verdict": gc, "basis": "stub"} if gc else None,
            "overall": {"verdict": overall, "summary": "stub path verdict"},
            "issue_for_curator": None if overall == "accept" else "stub: symptom-only issue",
            "routed_to_human": False,
        }
        return [{"final": json.dumps(out)}]
    # edge-evidence judge
    verdicts = [{
        "reference": ev.get("reference"),
        "checks": {},
        "rederived_supports": "SUPPORT",
        "agrees_with_curator": True,
        "confidence": "high",
    } for ev in (inp.get("evidence") or [])]
    return [{"final": json.dumps({"verdicts": verdicts, "edge_supported": bool(verdicts) or None})}]


# ── core orchestration ─────────────────────────────────────────────────────────

def _n_evidence_edges(doc: dict) -> int:
    return sum(1 for l in (doc.get("links") or []) if l.get("evidence"))


def judge_one(rec: dict, backend: Backend, *, pair_map: dict, kb_dir: Path,
              tools, max_iters: int, use_cache: bool) -> tuple[dict, dict]:
    """Judge a single path. Returns (blind_result, reveal_entry)."""
    file = rec["file"]
    doc = yaml.safe_load(file.read_text())
    g = doc.get("graph") or {}
    legacy_id, gold = resolve_legacy(file, doc, pair_map, kb_dir)
    reveal = {"blind_id": rec["blind_id"], "arm": rec["arm"],
              "source_file": str(file), "legacy_path_id": legacy_id}

    try:
        struct = structural_quality.analyze(file, LEX)
    except Exception:
        struct = None

    result = {
        "blind_id": rec["blind_id"],
        "record": {"drug": g.get("drug"), "disease": g.get("disease")},
        "n_edges": len(doc.get("links") or []),
        "n_evidence_edges": _n_evidence_edges(doc),
        "has_legacy": legacy_id is not None,
    }
    try:
        edge_verdicts = judge_edges(doc, backend, tools=tools, max_iters=max_iters, use_cache=use_cache)
        path_bundle = judge_path(doc, struct, edge_verdicts, backend, gold_path=gold,
                                 tools=tools, max_iters=max_iters, use_cache=use_cache)
        pv = path_bundle.get("verdict", {}) or {}
        result["edge_faithfulness"] = qp.edge_faithfulness(edge_verdicts)
        result["path_coherence"] = {
            "overall": _verdict_str(pv.get("overall")),
            "mechanism_is_accepted": _verdict_str(pv.get("mechanism_is_accepted")),
            "net_effect_correct": _verdict_str(pv.get("net_effect_correct")),
            "missing_step": _present(pv.get("missing_step")),
            "shortcut": _present(pv.get("no_shortcut_edge")),
            "issue_for_curator": pv.get("issue_for_curator"),
        }
        result["gold_comparison"] = _verdict_str(pv.get("gold_comparison"))
        if isinstance(pv, dict) and pv.get("_parse_error"):
            result["error"] = f"path verdict unparseable: {pv.get('_parse_error')}"
    except Exception as e:  # never let one bad path kill the batch
        result["error"] = f"{type(e).__name__}: {e}"
    return result, reveal


def _blank_verdict_counts() -> dict:
    return {v: 0 for v in _VERDICTS} | {"other": 0}


def aggregate(results: list[dict], reveal: list[dict]) -> dict:
    """Post-scoring aggregate: verdict + gold distributions, overall and per arm."""
    arm_of = {r["blind_id"]: r["arm"] for r in reveal}
    by_arm_verdict: dict[str, dict] = {}
    by_arm_gold: dict[str, dict] = {}
    verdict_counts = _blank_verdict_counts()
    gold_dist = {c: 0 for c in _GOLD_CLASSES} | {"other": 0}
    support_fracs = []
    n_with_gold = n_agree = 0
    agree_by_arm: dict[str, list[int]] = {}

    for r in results:
        arm = arm_of.get(r["blind_id"], "?")
        v = (r.get("path_coherence") or {}).get("overall")
        bucket = v if v in _VERDICTS else "other"
        verdict_counts[bucket] += 1
        by_arm_verdict.setdefault(arm, _blank_verdict_counts())[bucket] += 1

        ef = r.get("edge_faithfulness") or {}
        if ef.get("support_fraction") is not None:
            support_fracs.append(ef["support_fraction"])

        gc = r.get("gold_comparison")
        if r.get("has_legacy") and gc:
            gbucket = gc if gc in _GOLD_CLASSES else "other"
            gold_dist[gbucket] += 1
            by_arm_gold.setdefault(arm, {c: 0 for c in _GOLD_CLASSES} | {"other": 0})[gbucket] += 1
            n_with_gold += 1
            agrees = 1 if gc != "disagree" else 0     # agreement = judge did not call it a disagreement
            n_agree += agrees
            agree_by_arm.setdefault(arm, []).append(agrees)

    return {
        "path_verdict_counts": verdict_counts,
        "path_verdict_counts_by_arm": by_arm_verdict,
        "edge_support_fraction_mean": round(sum(support_fracs) / len(support_fracs), 3) if support_fracs else None,
        "gold_comparison_distribution": gold_dist,
        "gold_comparison_distribution_by_arm": by_arm_gold,
        "agreement_with_legacy": {
            "n_with_gold": n_with_gold, "n_agree": n_agree,
            "fraction": round(n_agree / n_with_gold, 3) if n_with_gold else None,
        },
        "agreement_with_legacy_by_arm": {
            arm: {"n_with_gold": len(v), "n_agree": sum(v),
                  "fraction": round(sum(v) / len(v), 3) if v else None}
            for arm, v in agree_by_arm.items()
        },
    }


def build_plan(blinded: list[dict], pair_map: dict, kb_dir: Path) -> tuple[list[dict], list[dict]]:
    """Dry-run: per-path plan + reveal, no judging."""
    plan, reveal = [], []
    for rec in blinded:
        doc = yaml.safe_load(rec["file"].read_text())
        g = doc.get("graph") or {}
        legacy_id, gold = resolve_legacy(rec["file"], doc, pair_map, kb_dir)
        plan.append({
            "blind_id": rec["blind_id"],
            "record": {"drug": g.get("drug"), "disease": g.get("disease")},
            "n_edges": len(doc.get("links") or []),
            "n_evidence_edges": _n_evidence_edges(doc),
            "has_legacy": legacy_id is not None,
            "gold_path_loaded": gold is not None,
            "est_judge_calls": _n_evidence_edges(doc) + 1,   # one edge call per evidenced edge + one path call
        })
        reveal.append({"blind_id": rec["blind_id"], "arm": rec["arm"],
                       "source_file": str(rec["file"]), "legacy_path_id": legacy_id})
    return plan, reveal


# ── rendering ──────────────────────────────────────────────────────────────────

def _md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return "\n".join(out)


def render_markdown(report: dict) -> str:
    j = report["judge"]
    lines = [
        "# Blinded judge results",
        "",
        f"- generated: `{report['generated_at']}`",
        f"- mode: **{report['mode']}**",
        f"- judge: {j['note']}",
        f"- paths: {report['n_paths']}  ·  arms: {', '.join(sorted({r['arm'] for r in report['reveal_key']}))}",
        f"- seed: {report['config']['seed']}  ·  eval_pairs: {report['config']['eval_pairs'] or '(none)'}",
        "",
        "> The judge saw only path *content* (nodes / predicates / evidence / drug+disease); it was never",
        "> told the source model. The per-path table below is blind (drug→disease is shared across arms).",
        "> The reveal key and per-arm aggregate are joined in only after scoring.",
        "",
    ]

    if report["mode"] == "dry-run":
        lines += ["## Plan (no judging performed)", ""]
        rows = [[p["blind_id"], f"{p['record']['drug']} → {p['record']['disease']}",
                 p["n_edges"], p["n_evidence_edges"],
                 "yes" if p["has_legacy"] else "no", p["est_judge_calls"]]
                for p in report["results"]]
        lines.append(_md_table(
            ["blind_id", "drug → disease", "edges", "evidence-edges", "legacy?", "est. judge calls"], rows))
        total_calls = sum(p["est_judge_calls"] for p in report["results"])
        lines += ["", f"Estimated total judge calls if run: **{total_calls}** "
                      f"({report['n_paths']} paths).",
                  "", "Re-run with `--run` (needs an API key) for a real pass, or `--stub` for an offline "
                      "orchestration check.", ""]
        lines += _reveal_section(report)
        return "\n".join(lines)

    # run / stub mode
    lines += ["## Per-path verdicts (blind)", ""]
    rows = []
    for r in report["results"]:
        ef = r.get("edge_faithfulness") or {}
        support = (f"{ef.get('n_support')}/{ef.get('n_evidence')}"
                   if ef.get("n_evidence") else "—")
        pc = r.get("path_coherence") or {}
        rows.append([
            r["blind_id"], f"{r['record']['drug']} → {r['record']['disease']}",
            r["n_evidence_edges"], support,
            (pc.get("overall") or (r.get("error") and "ERROR") or "—"),
            (r.get("gold_comparison") or ("—" if r.get("has_legacy") else "n/a")),
        ])
    lines.append(_md_table(
        ["blind_id", "drug → disease", "evidence-edges", "edge SUPPORT", "path verdict", "vs legacy"], rows))

    agg = report["aggregate"]
    lines += ["", "## Aggregate (unblinded after scoring)", "",
              "**Path-coherence verdicts**", ""]
    headers = ["arm", *(_VERDICTS), "other"]
    rows = []
    for arm, c in sorted(agg["path_verdict_counts_by_arm"].items()):
        rows.append([arm, *(c[v] for v in _VERDICTS), c["other"]])
    tot = agg["path_verdict_counts"]
    rows.append(["**all**", *(tot[v] for v in _VERDICTS), tot["other"]])
    lines.append(_md_table(headers, rows))

    al = agg["agreement_with_legacy"]
    al_frac = "—" if al["fraction"] is None else f"{al['fraction']:.0%}"
    lines += ["", "**Agreement with legacy** (judge did not classify the pair as `disagree`, "
                  "among paths that have a legacy path)", "",
              f"- overall: {al['n_agree']}/{al['n_with_gold']} ({al_frac})"]
    for arm, a in sorted(agg["agreement_with_legacy_by_arm"].items()):
        frac = "—" if a["fraction"] is None else f"{a['fraction']:.0%}"
        lines.append(f"- {arm}: {a['n_agree']}/{a['n_with_gold']} ({frac})")

    gd = agg["gold_comparison_distribution"]
    if any(gd.values()):
        lines += ["", "**Gold-comparison distribution**", "",
                  _md_table(["classification", "count"],
                            [[c, gd[c]] for c in (*_GOLD_CLASSES, "other")])]

    if agg["edge_support_fraction_mean"] is not None:
        lines += ["", f"Mean per-path edge SUPPORT fraction: **{agg['edge_support_fraction_mean']}**"]

    errs = [r for r in report["results"] if r.get("error")]
    if errs:
        lines += ["", "## Errors", ""]
        for r in errs:
            lines.append(f"- {r['blind_id']}: {r['error']}")

    lines += [""] + _reveal_section(report)
    return "\n".join(lines)


def _reveal_section(report: dict) -> list[str]:
    lines = ["## Reveal key", "",
             "> Do not consult before scoring is complete. Maps each blind id to its source arm/file.",
             ""]
    rows = [[e["blind_id"], e["arm"], e.get("legacy_path_id") or "—", e["source_file"]]
            for e in sorted(report["reveal_key"], key=lambda e: e["blind_id"])]
    lines.append(_md_table(["blind_id", "arm", "legacy_path_id", "source_file"], rows))
    return lines


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _write_outputs(out_dir: Path, report: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "blinded_judge_results.json"
    md_path = out_dir / "blinded_judge_results.md"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    md_path.write_text(render_markdown(report))
    return json_path, md_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Blinded LLM-judge harness over a pilot's curated path YAMLs.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="DIR or LABEL=DIR per curation arm (dir of *.yaml)")
    ap.add_argument("--out-dir", required=True, help="where to write results (JSON + Markdown)")
    ap.add_argument("--eval-pairs", help="eval_pairs.yaml mapping pair id -> legacy_path_id (enables 'vs legacy')")
    ap.add_argument("--kb-dir", default=str(REPO / "kb" / "paths"),
                    help="read-only dir of legacy path YAMLs (default kb/paths)")
    ap.add_argument("--run", action="store_true", help="do the real judging (needs an API key)")
    ap.add_argument("--stub", action="store_true",
                    help="run the full orchestration with the offline StubBackend (no API, for tests/CI)")
    ap.add_argument("--judge-provider", choices=("auto", "openai", "anthropic"), default="auto",
                    help="judge model family; 'auto' prefers a different family than the curator (§6c)")
    ap.add_argument("--judge-model", help="override the judge model id")
    ap.add_argument("--curator-family", default="anthropic",
                    help="the pilot's curator family, for the independence note (default anthropic/Claude)")
    ap.add_argument("--tools", choices=("critic", "default"), default="critic",
                    help="grounding tool set: 'critic' = independent reading (search/read + read-only cited cache + ChEMBL); "
                         "'default' = cited source + ChEMBL only")
    ap.add_argument("--seed", type=int, default=1234, help="blinding shuffle seed (reproducible)")
    ap.add_argument("--max-iters", type=int, default=6, help="tool-loop cap per judge call")
    ap.add_argument("--no-cache", action="store_true", help="don't reuse the on-disk verdict cache")
    args = ap.parse_args(argv)

    items = discover_inputs(args.inputs)
    if not items:
        print("no *.yaml paths found in the given inputs", file=sys.stderr)
        return 2
    blinded = assign_blind_ids(items, args.seed)
    pair_map = load_eval_pairs(args.eval_pairs)
    kb_dir = Path(args.kb_dir)

    prov, model, jnote, key_ok = resolve_judge(args.judge_provider, args.judge_model, args.curator_family)

    base = {
        "tool": "run_blinded_judge",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_paths": len(blinded),
        "config": {"seed": args.seed, "kb_dir": str(kb_dir),
                   "eval_pairs": args.eval_pairs, "max_iters": args.max_iters,
                   "use_cache": not args.no_cache, "tools": args.tools},
    }

    # ── mode: dry-run (default) ──────────────────────────────────────────────
    if not args.run and not args.stub:
        plan, reveal = build_plan(blinded, pair_map, kb_dir)
        report = {**base, "mode": "dry-run",
                  "judge": {"provider": prov, "model": model,
                            "note": f"WOULD USE {jnote}"
                                    + ("" if key_ok else "  [key NOT set — --run will fail; use --stub for offline]")},
                  "results": plan, "reveal_key": reveal}
        json_path, md_path = _write_outputs(Path(args.out_dir), report)
        print(f"[dry-run] planned {len(plan)} paths across {len({r['arm'] for r in reveal})} arm(s).")
        print(f"          judge that WOULD run: {jnote}")
        print(f"          est. judge calls: {sum(p['est_judge_calls'] for p in plan)}")
        print(f"  wrote {json_path}\n        {md_path}")
        print("  (no API called — this is the default. Use --run for a real pass or --stub for an offline check.)")
        return 0

    # ── build the backend ────────────────────────────────────────────────────
    if args.stub:
        backend: Backend | None = StubBackend(stub_responder)
        jnote = "STUB (offline, deterministic — NO API)"
        note = jnote
    else:  # --run
        backend, note = build_backend(prov, model)
        if backend is None:
            print(f"cannot run the judge: {note}. "
                  f"Set the key, choose --judge-provider, or use --stub for an offline check.",
                  file=sys.stderr)
            return 2
        note = f"{jnote}  [{note}]"

    tools = None  # let each judge use its default tool set…
    if args.tools == "critic":
        from judge.grounding import critic_tools
        tools = critic_tools()
    elif args.tools == "default":
        from judge.grounding import default_tools
        tools = default_tools()

    results, reveal = [], []
    for rec in blinded:
        res, rev = judge_one(rec, backend, pair_map=pair_map, kb_dir=kb_dir, tools=tools,
                             max_iters=args.max_iters, use_cache=not args.no_cache)
        results.append(res)
        reveal.append(rev)
        v = (res.get("path_coherence") or {}).get("overall") or (res.get("error") and "error") or "?"
        print(f"  {rec['blind_id']}  {res['record']['drug']} → {res['record']['disease']:<28.28}  {v}")

    report = {**base, "mode": "stub" if args.stub else "run",
              "judge": {"provider": ("stub" if args.stub else prov), "model": (None if args.stub else model),
                        "note": note},
              "results": results, "reveal_key": reveal,
              "aggregate": aggregate(results, reveal)}
    json_path, md_path = _write_outputs(Path(args.out_dir), report)
    agg = report["aggregate"]
    print(f"\nverdicts: {agg['path_verdict_counts']}")
    al = agg["agreement_with_legacy"]
    if al["n_with_gold"]:
        al_frac = "" if al["fraction"] is None else f"{al['fraction']:.0%}"
        print(f"agreement-with-legacy: {al['n_agree']}/{al['n_with_gold']} ({al_frac})")
    print(f"wrote {json_path}\n      {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
