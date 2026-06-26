"""
DrugMechDB QC orchestrator — runs Layers 1-4 against per-path YAML files,
honoring the legacy / ai_curated profile selector defined in PRD v3 §5.3.5.

Layers:
  Layer 1 — LinkML schema validation       (scripts/validate_schema.py)
  Layer 2 — Node ontology check            (scripts/validate_node_ontology.py)
  Layer 3 — Biolink predicate validation   (scripts/validate_predicates.py)
  Layer 4 — Reference / snippet verify     (scripts/validate_references.py)

Profile rules:
  legacy      : Layers 1, 2, 3            (evidence not required; Layer 4 skipped)
  ai_curated  : Layers 1, 2, 3, 4         (evidence required on every edge)
  auto        : per-file detection:
                  - if file has any `evidence` block on an edge -> ai_curated
                  - else                                        -> legacy

Usage:
    just qc                       # all files, auto profile
    just qc --profile legacy      # force legacy
    just qc --profile ai_curated  # force ai_curated
    just qc kb/paths/X.yaml       # single file
    just qc --layer 1             # just Layer 1
    just qc --json                # machine-readable output

The justfile target wraps this script; the script is also runnable directly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"


LAYER_SCRIPTS = {
    1: REPO / "scripts" / "validate_schema.py",
    2: REPO / "scripts" / "validate_node_ontology.py",
    3: REPO / "scripts" / "validate_predicates.py",
    4: REPO / "scripts" / "validate_references.py",
}

PROFILE_LAYERS = {
    "legacy": [1, 2, 3],
    "ai_curated": [1, 2, 3, 4],
}


def python_bin() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def has_evidence(path: Path) -> bool:
    with path.open() as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        return False
    for link in doc.get("links") or []:
        if isinstance(link, dict) and link.get("evidence"):
            return True
    return False


def detect_profile(path: Path) -> str:
    return "ai_curated" if has_evidence(path) else "legacy"


def iter_files(targets: Iterable[str]) -> list[Path]:
    targets = list(targets)
    if not targets:
        return sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(q for q in p.glob("*.yaml") if q.name != "_index.yaml"))
        elif p.is_file():
            files.append(p)
    return files


def run_layer(layer: int, files: list[Path], json_out: bool, offline: bool = False) -> tuple[int, str]:
    """Invoke a layer script against a set of files. Returns (exit_code, stdout_or_json)."""
    cmd = [python_bin(), str(LAYER_SCRIPTS[layer])]
    if json_out:
        cmd.append("--json")
    # Layer 4 is the only layer that fetches from the network; --offline pins it
    # to the committed references_cache/ for deterministic CI / reproducible runs.
    if offline and layer == 4:
        cmd.append("--offline")
    cmd.extend(str(f) for f in files)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", help="Files or directories. Default: kb/paths/")
    parser.add_argument(
        "--profile",
        choices=("auto", "legacy", "ai_curated"),
        default="auto",
        help="Validation profile. `auto` chooses per-file (default).",
    )
    parser.add_argument(
        "--layer",
        type=int,
        choices=(1, 2, 3, 4),
        help="Run only the specified layer.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON summary"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Layer 4 only: verify snippets against the committed references_cache/ "
        "without fetching PubMed (deterministic CI / reproducible runs).",
    )
    args = parser.parse_args()

    files = iter_files(args.targets)
    if not files:
        print("No files to check.", file=sys.stderr)
        return 2

    # Group files by effective profile
    if args.profile == "auto":
        buckets: dict[str, list[Path]] = {"legacy": [], "ai_curated": []}
        for f in files:
            buckets[detect_profile(f)].append(f)
    else:
        buckets = {args.profile: files}

    if args.layer:
        layers = [args.layer]
    else:
        # Union across active profiles, preserving order
        seen = []
        for profile, paths in buckets.items():
            if not paths:
                continue
            for layer in PROFILE_LAYERS[profile]:
                if layer not in seen:
                    seen.append(layer)
        layers = sorted(seen)

    results: list[dict] = []
    overall_fail = False
    for layer in layers:
        # For Layer 4, only run against files in profiles that include it
        layer_files: list[Path] = []
        for profile, paths in buckets.items():
            if layer in PROFILE_LAYERS[profile]:
                layer_files.extend(paths)
        if not layer_files:
            continue
        if not args.json:
            print(f"--- Layer {layer} ({LAYER_SCRIPTS[layer].name}) — {len(layer_files)} file(s) ---")
        code, out = run_layer(layer, layer_files, json_out=args.json, offline=args.offline)
        results.append({"layer": layer, "files": len(layer_files), "exit_code": code, "output": out})
        if code != 0:
            overall_fail = True
        if not args.json:
            print(out.rstrip())
            print()

    if args.json:
        print(json.dumps({
            "profile": args.profile,
            "layers_run": layers,
            "profile_counts": {p: len(ps) for p, ps in buckets.items()},
            "results": results,
            "overall_pass": not overall_fail,
        }, indent=2, default=str))
    else:
        print(f"=== QC summary ===")
        for r in results:
            status = "PASS" if r["exit_code"] == 0 else "FAIL"
            print(f"  Layer {r['layer']:>1}: {status}  ({r['files']} files)")
        if args.profile == "auto":
            print(f"  Profile split: legacy={len(buckets.get('legacy', []))} ai_curated={len(buckets.get('ai_curated', []))}")
        print(f"  Overall: {'PASS' if not overall_fail else 'FAIL'}")

    return 0 if not overall_fail else 1


if __name__ == "__main__":
    sys.exit(main())
