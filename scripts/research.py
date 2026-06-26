"""External research-agent orchestrator for DrugMechDB curation.

Calls a provider's research agent for a (drug, disease) pair and writes a
markdown dossier to research/<drug_slug>_<disease_slug>-<provider>.md. The
curation agent consumes the dossier as advisory input — PMIDs are
re-verified via scripts/pubmed_fetch.py and snippets are re-extracted from
the cached PubMed abstract before landing in any path YAML.

Subcommands:
  list                              Show registered providers and their env requirements.
  run <provider> <drug> <disease>   Execute research. Default: claude.
  cache-info <provider> <drug> <disease>   Show cached dossier metadata (no network).

Examples:
  python scripts/research.py list
  python scripts/research.py run claude "Aspirin" "Myocardial Infarction"
  python scripts/research.py run claude "Aspirin" "Myocardial Infarction" --force
  python scripts/research.py cache-info claude "Aspirin" "Myocardial Infarction"

Environment:
  ANTHROPIC_API_KEY   required for the claude provider
  PERPLEXITY_API_KEY  required for the perplexity provider (not yet implemented)
  ASTA_API_KEY        required for the asta provider (not yet implemented)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from research_providers import PROVIDERS  # noqa: E402
from research_providers import cache as cache_mod  # noqa: E402


# ─── list ────────────────────────────────────────────────────────────────


def cmd_list(args: argparse.Namespace) -> int:
    print(f"{'name':14} {'default_model':28} {'env vars required':35} status")
    print("-" * 90)
    for name, cls in PROVIDERS.items():
        env = ", ".join(cls.requires_env) or "—"
        env_status_parts = []
        for var in cls.requires_env:
            env_status_parts.append("set" if os.environ.get(var) else "MISSING")
        env_status = ", ".join(env_status_parts) if env_status_parts else "ok"
        impl = "ready" if _is_implemented(cls) else "stub (not yet implemented)"
        print(f"{name:14} {cls.default_model:28} {env:35} {impl} | env: {env_status}")
    return 0


def _is_implemented(cls) -> bool:
    """Return True if the provider's run() doesn't immediately raise NotImplementedError."""
    src = (cls.run.__doc__ or "") + (cls.__module__ or "")
    # Better: check the source for NotImplementedError. Quick heuristic:
    import inspect
    try:
        body = inspect.getsource(cls.run)
        return "NotImplementedError" not in body
    except OSError:
        return True


# ─── run ─────────────────────────────────────────────────────────────────


def cmd_run(args: argparse.Namespace) -> int:
    provider_name = args.provider
    if provider_name not in PROVIDERS:
        print(f"unknown provider: {provider_name!r}", file=sys.stderr)
        print(f"  available: {', '.join(PROVIDERS.keys())}", file=sys.stderr)
        return 2

    drug = args.drug
    disease = args.disease

    # Cache check
    if not args.force:
        fresh = cache_mod.load_if_fresh(drug, disease, provider_name, ttl_days=args.ttl_days)
        if fresh is not None:
            if args.json:
                fm, _body = cache_mod.load(fresh)
                print(json.dumps({"cached": True, "path": str(fresh), "frontmatter": fm}, default=str, indent=2))
            else:
                print(f"CACHED  {fresh.relative_to(REPO)}")
            return 0

    cls = PROVIDERS[provider_name]
    provider = cls(model=args.model) if args.model else cls()

    try:
        dossier = provider.run(drug, disease)
    except NotImplementedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR ({type(e).__name__}): {e}", file=sys.stderr)
        return 1

    path = cache_mod.write(dossier, ttl_days=args.ttl_days)

    if args.json:
        print(json.dumps({
            "cached": False,
            "path": str(path),
            "provider": dossier.provider,
            "model": dossier.model,
            "candidate_pmids": dossier.candidate_pmids,
            "notes": dossier.notes,
        }, indent=2))
    else:
        print(f"FETCHED  {path.relative_to(REPO)}")
        print(f"  provider     : {dossier.provider}")
        print(f"  model        : {dossier.model}")
        print(f"  PMIDs found  : {len(dossier.candidate_pmids)}")
        for pmid in dossier.candidate_pmids[:10]:
            print(f"    {pmid}")
        if len(dossier.candidate_pmids) > 10:
            print(f"    …and {len(dossier.candidate_pmids) - 10} more")
        if dossier.notes:
            print(f"  notes        : {dossier.notes}")
    return 0


# ─── cache-info ──────────────────────────────────────────────────────────


def cmd_cache_info(args: argparse.Namespace) -> int:
    path = cache_mod.cache_path(args.drug, args.disease, args.provider)
    loaded = cache_mod.load(path)
    if not loaded:
        if args.json:
            print(json.dumps({"cached": False, "path": str(path)}))
        else:
            print(f"NOT CACHED  {path.relative_to(REPO)}")
        return 1
    fm, body = loaded
    fresh = cache_mod.is_fresh(fm)
    if args.json:
        print(json.dumps({
            "cached": True, "fresh": fresh, "path": str(path),
            "frontmatter": fm, "body_bytes": len(body),
        }, default=str, indent=2))
    else:
        print(f"{'FRESH' if fresh else 'STALE'}  {path.relative_to(REPO)}")
        for k, v in fm.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
            else:
                print(f"  {k}: {v}")
    return 0


# ─── main ────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show registered providers")

    p_run = sub.add_parser("run", help="Run a provider")
    p_run.add_argument("provider", choices=list(PROVIDERS.keys()))
    p_run.add_argument("drug")
    p_run.add_argument("disease")
    p_run.add_argument("--model", help="Override the provider's default model")
    p_run.add_argument("--force", action="store_true", help="Bypass cache freshness check")
    p_run.add_argument("--ttl-days", type=int, default=cache_mod.DEFAULT_TTL_DAYS,
                       help=f"Cache TTL in days (default {cache_mod.DEFAULT_TTL_DAYS})")
    p_run.add_argument("--json", action="store_true", help="Machine-readable output")

    p_info = sub.add_parser("cache-info", help="Show cache state for a triple")
    p_info.add_argument("provider")
    p_info.add_argument("drug")
    p_info.add_argument("disease")
    p_info.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "cache-info":
        return cmd_cache_info(args)
    parser.error("unknown subcommand")


if __name__ == "__main__":
    sys.exit(main())
