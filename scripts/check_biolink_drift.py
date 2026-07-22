"""
Biolink predicate-vocabulary drift monitor.

Detects when the upstream Biolink Model's predicate vocabulary has drifted away
from the predicate set this project accepts, and prepares the drift for a HUMAN
to review. It is a *monitor and a report generator*, never an editor.

What it compares
----------------
Ours (two committed artifacts, read-only):
  - the accepted predicate enum
      src/drugmechdb/schema/biolink_predicates.yaml  (BiolinkPredicate enum)
  - the polarity lexicon
      scripts/quality/predicate_polarity.yaml        (sign / role / confidence)

Theirs (fetched, cached):
  - the latest Biolink Model YAML from GitHub raw. Predicates are the `slots`
    whose `is_a`/`mixins` ancestry reaches the root predicate slot `related to`.

What it computes
----------------
  removed     our predicate is no longer a Biolink predicate (e.g. dropped in the
              v2->v4 qualifier refactor: `positively regulates`, `increases
              activity of`, ...). These are the highest-signal drift.
  deprecated  our predicate still exists upstream but is flagged `deprecated`.
  renamed     our predicate maps (by CURIE) to a Biolink slot whose canonical
              name now differs from our surface form.
  added       Biolink predicates absent from our enum (informational; large).
  polarity-coverage  schema predicates with no polarity entry, and stale
              polarity entries with no schema predicate.

CARDINAL RULES (enforced in code, not just documented)
-------------------------------------------------------
  1. This script is READ-ONLY with respect to committed files. It writes reports
     only to stdout or to an explicit --report-dir (a scratch path). It refuses
     to write its --emit-enum output onto the committed schema or polarity file.
  2. Any resulting code/schema change is delivered as a HUMAN-reviewed DRAFT pull
     request, NEVER auto-committed or auto-merged. `--emit-enum` therefore emits a
     *drift-annotated copy* of the enum (all values preserved, drift flagged with
     inline `# BIOLINK-DRIFT` markers) — it never deletes a predicate, because
     dropping predicates would silently break existing records.
  3. Polarity SIGNS are NEVER assigned by this tool. Predicates that need a sign
     decision (new / removed / uncovered) are only *listed* for a human.

Usage
-----
    python scripts/check_biolink_drift.py                       # report to stdout
    python scripts/check_biolink_drift.py --show-added          # also list added preds
    python scripts/check_biolink_drift.py --json                # machine-readable
    python scripts/check_biolink_drift.py --report-dir <dir>    # also write md + json
    python scripts/check_biolink_drift.py --emit-enum <path>    # annotated enum copy
    python scripts/check_biolink_drift.py --offline             # cache only, no network
    python scripts/check_biolink_drift.py --fail-on-drift       # exit 1 if drift found

Exit status: 0 normally (monitor). With --fail-on-drift: 1 if any removed/renamed/
deprecated predicate is found, else 0. 2 on a fetch/parse error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "src" / "drugmechdb" / "schema" / "biolink_predicates.yaml"
POLARITY = REPO / "scripts" / "quality" / "predicate_polarity.yaml"

# Latest Biolink Model. `master` == "latest" for a drift monitor; pin with
# --biolink-ref <tag> for a reproducible run. The fetched YAML's own `version`
# field is recorded in every report for provenance.
DEFAULT_BIOLINK_REF = "master"
BIOLINK_RAW = (
    "https://raw.githubusercontent.com/biolink/biolink-model/{ref}/biolink-model.yaml"
)
# Cache lives under .cache/ which is gitignored — never committed.
DEFAULT_CACHE = REPO / ".cache" / "biolink" / "biolink-model.yaml"

PREDICATE_ROOT = "related to"  # root of the Biolink predicate hierarchy


# ── our side ────────────────────────────────────────────────────────────────
def load_our_enum() -> dict[str, str | None]:
    """surface form -> biolink CURIE (`meaning`), or None when unmapped."""
    doc = yaml.safe_load(SCHEMA.read_text())
    pv = doc["enums"]["BiolinkPredicate"]["permissible_values"]
    return {name: (spec or {}).get("meaning") for name, spec in pv.items()}


def load_polarity() -> dict[str, dict]:
    doc = yaml.safe_load(POLARITY.read_text())
    return {k: (v or {}) for k, v in (doc.get("predicates") or {}).items()}


# ── biolink side ──────────────────────────────────────────────────────────────
def fetch_biolink_yaml(url: str, cache: Path, *, refresh: bool, offline: bool) -> str:
    if cache.exists() and not refresh:
        return cache.read_text()
    if offline:
        raise RuntimeError(
            f"--offline set but no cache at {cache}. Run once online (or with "
            f"--refresh) to populate the cache first."
        )
    import httpx  # local import: offline/cache runs need no network dep

    resp = httpx.get(url, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(resp.text)
    return resp.text


def _slot_uri(name: str, spec: dict) -> str:
    if spec.get("slot_uri"):
        return spec["slot_uri"]
    return "biolink:" + name.replace(" ", "_")


def biolink_predicates(bl: dict) -> tuple[dict[str, str], set[str], set[str]]:
    """
    Return (name -> CURIE for every predicate, set of CURIEs, set of deprecated names).

    A slot is a predicate iff its is_a/mixins ancestry reaches `related to`.
    """
    slots: dict[str, dict] = {k: (v or {}) for k, v in (bl.get("slots") or {}).items()}

    def is_predicate(name: str) -> bool:
        seen: set[str] = set()
        stack = [name]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            if n == PREDICATE_ROOT:
                return True
            spec = slots.get(n)
            if not spec:
                continue
            if spec.get("is_a"):
                stack.append(spec["is_a"])
            stack.extend(spec.get("mixins") or [])
        return False

    preds: dict[str, str] = {}
    deprecated: set[str] = set()
    for name, spec in slots.items():
        if is_predicate(name):
            preds[name] = _slot_uri(name, spec)
            if spec.get("deprecated"):
                deprecated.add(name)
    return preds, set(preds.values()), deprecated


# ── drift computation ─────────────────────────────────────────────────────────
def compute_drift(
    our_enum: dict[str, str | None],
    polarity: dict[str, dict],
    bl_pred_names: dict[str, str],
    bl_curies: set[str],
    bl_deprecated: set[str],
) -> dict:
    curie_to_name = {curie: name for name, curie in bl_pred_names.items()}

    removed: list[dict] = []       # ours, gone from biolink entirely
    deprecated: list[dict] = []    # ours, still present but flagged deprecated
    renamed: list[dict] = []       # ours, present by CURIE but canonical name changed
    present: list[str] = []

    for surface, meaning in our_enum.items():
        name_hit = surface in bl_pred_names
        curie_hit = bool(meaning) and meaning in bl_curies
        if not (name_hit or curie_hit):
            removed.append({"predicate": surface, "meaning": meaning})
            continue
        present.append(surface)
        # canonical name for our CURIE, if biolink still defines it
        bl_name = curie_to_name.get(meaning) if meaning else None
        if bl_name and bl_name != surface:
            renamed.append({"predicate": surface, "meaning": meaning, "biolink_name": bl_name})
        # deprecated upstream (match by surface name or by canonical name)
        if surface in bl_deprecated or (bl_name and bl_name in bl_deprecated):
            deprecated.append({"predicate": surface, "meaning": meaning})

    our_curies = {c for c in our_enum.values() if c}
    added = sorted(name for name, curie in bl_pred_names.items() if curie not in our_curies)

    # internal polarity coverage (drift between our own two artifacts)
    schema_keys = set(our_enum)
    pol_keys = set(polarity)
    missing_polarity = sorted(schema_keys - pol_keys)
    stale_polarity = sorted(pol_keys - schema_keys)
    review_polarity = sorted(k for k, v in polarity.items() if v.get("confidence") == "review")

    # Predicates that need a HUMAN polarity-sign decision. We list; never assign.
    need_sign: dict[str, list[str]] = {
        "removed_from_biolink": sorted(r["predicate"] for r in removed),
        "deprecated_in_biolink": sorted(d["predicate"] for d in deprecated),
        "missing_polarity_entry": missing_polarity,
    }

    return {
        "present": sorted(present),
        "removed": sorted(removed, key=lambda r: r["predicate"]),
        "deprecated": sorted(deprecated, key=lambda d: d["predicate"]),
        "renamed": sorted(renamed, key=lambda r: r["predicate"]),
        "added": added,
        "polarity": {
            "missing_polarity_entry": missing_polarity,
            "stale_polarity_entry": stale_polarity,
            "already_flagged_review": review_polarity,
        },
        "needs_human_polarity_decision": need_sign,
    }


# ── reporting ──────────────────────────────────────────────────────────────────
def render_report(drift: dict, meta: dict, *, show_added: bool) -> str:
    n_ours = meta["our_enum_size"]
    lines: list[str] = []
    A = lines.append

    A("# Biolink predicate-vocabulary drift report")
    A("")
    A(f"- Biolink source : {meta['biolink_url']}")
    A(f"- Biolink version: {meta['biolink_version']}  ({meta['biolink_predicate_count']} predicates)")
    A(f"- Our enum       : {n_ours} predicates ({SCHEMA.relative_to(REPO)})")
    A(f"- Polarity lexicon: {meta['polarity_size']} entries ({POLARITY.relative_to(REPO)})")
    A("")
    A("> This report is advisory. Any schema/polarity change goes through a")
    A("> HUMAN-reviewed DRAFT pull request — nothing here is auto-applied, and no")
    A("> polarity sign is ever assigned automatically.")
    A("")

    A("## Summary")
    A("")
    A(f"- present in Biolink : {len(drift['present'])}/{n_ours}")
    A(f"- REMOVED            : {len(drift['removed'])}  (our predicate no longer in Biolink)")
    A(f"- deprecated upstream: {len(drift['deprecated'])}")
    A(f"- renamed upstream   : {len(drift['renamed'])}")
    A(f"- added (in Biolink, not ours): {len(drift['added'])}  (informational)")
    A("")

    if drift["removed"]:
        A("## REMOVED — our predicate is no longer a Biolink predicate")
        A("")
        A("These edges' keys are no longer valid in the current Biolink model (most were")
        A("folded into `regulates`/`affects` + qualifiers in the v2->v4 refactor). Removing")
        A("them from the enum would break existing records, so this needs a human decision")
        A("(the locked policy is to translate at the publish/export layer, not migrate data).")
        A("")
        for r in drift["removed"]:
            A(f"  - {r['predicate']:<28} {r['meaning'] or '(no biolink mapping)'}")
        A("")

    if drift["deprecated"]:
        A("## DEPRECATED — present upstream but flagged deprecated")
        A("")
        for d in drift["deprecated"]:
            A(f"  - {d['predicate']:<28} {d['meaning'] or ''}")
        A("")

    if drift["renamed"]:
        A("## RENAMED — our CURIE resolves to a different Biolink canonical name")
        A("")
        for r in drift["renamed"]:
            A(f"  - {r['predicate']:<28} now '{r['biolink_name']}'  ({r['meaning']})")
        A("")

    A("## Polarity-lexicon coverage (internal consistency)")
    A("")
    pol = drift["polarity"]
    A(f"  - schema predicates with NO polarity entry : {len(pol['missing_polarity_entry'])}")
    for p in pol["missing_polarity_entry"]:
        A(f"      + {p}")
    A(f"  - polarity entries not in schema (stale)   : {len(pol['stale_polarity_entry'])}")
    for p in pol["stale_polarity_entry"]:
        A(f"      + {p}")
    A(f"  - polarity entries already flagged review  : {len(pol['already_flagged_review'])}")
    A("")

    A("## Predicates needing a HUMAN polarity-sign decision")
    A("")
    A("(Listed only — this tool never assigns a sign.)")
    need = drift["needs_human_polarity_decision"]
    for bucket, items in need.items():
        A(f"  {bucket} ({len(items)}):")
        for p in items:
            A(f"      + {p}")
    A("")

    if show_added:
        A(f"## ADDED — {len(drift['added'])} Biolink predicates not in our enum (informational)")
        A("")
        A("Adoption is a curator decision; each adopted predicate needs a human polarity sign.")
        A("")
        for p in drift["added"]:
            A(f"  - {p}")
        A("")
    else:
        A(f"(Run with --show-added to list the {len(drift['added'])} Biolink predicates we don't use.)")
        A("")

    return "\n".join(lines)


# ── proposed (annotated) enum for the guarded draft-PR step ─────────────────────
def emit_annotated_enum(drift: dict, meta: dict) -> str:
    """
    Return a drift-ANNOTATED copy of the enum for a human-reviewed DRAFT PR.

    It preserves the committed enum verbatim (comments, order, frequencies) and
    only INSERTS `# BIOLINK-DRIFT` marker lines above each drifted predicate,
    plus a DRAFT banner. It NEVER deletes a predicate and NEVER assigns polarity —
    dropping predicates would silently break existing records, so the human decides.
    """
    ver = meta["biolink_version"]
    flags: dict[str, str] = {}
    for r in drift["removed"]:
        flags[r["predicate"]] = f"removed from Biolink v{ver}"
    for d in drift["deprecated"]:
        flags.setdefault(d["predicate"], f"deprecated in Biolink v{ver}")
    for r in drift["renamed"]:
        flags.setdefault(r["predicate"], f"renamed in Biolink v{ver} -> '{r['biolink_name']}'")

    banner = [
        "# ============================================================================",
        "# DRAFT — Biolink drift annotations (auto-generated, HUMAN REVIEW REQUIRED)",
        f"# Generated against Biolink v{ver}. Lines flagged `# !! BIOLINK-DRIFT` below",
        "# mark predicates whose upstream status changed. This file is a REVIEW AID:",
        "#   * no predicate was removed (that would break existing records),",
        "#   * no polarity sign was assigned,",
        "#   * apply changes only via a reviewed pull request.",
        "# ============================================================================",
    ]

    out: list[str] = list(banner)
    for raw in SCHEMA.read_text().splitlines():
        name = _enum_header_name(raw)
        if name and name in flags:
            indent = raw[: len(raw) - len(raw.lstrip())]
            out.append(f"{indent}# !! BIOLINK-DRIFT: {flags[name]} — human review required; do NOT auto-apply")
        out.append(raw)
    return "\n".join(out) + "\n"


def _enum_header_name(raw: str) -> str | None:
    """If `raw` is a 6-space-indented permissible-value header, return its name."""
    if not raw.startswith("      ") or raw.startswith("       "):
        return None
    body = raw[6:]
    if body.startswith("#") or not body.strip():
        return None
    # header looks like "positively regulates:   # 6,630 uses"
    key = body.split(":", 1)[0]
    if ":" not in body or not key.strip():
        return None
    return key.strip()


# ── main ────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--biolink-ref", default=DEFAULT_BIOLINK_REF,
                    help="Biolink model git ref (branch/tag). Default: master (=latest).")
    ap.add_argument("--biolink-url", default=None,
                    help="Override the full Biolink model YAML URL.")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE,
                    help="Local cache path for the fetched Biolink YAML (gitignored).")
    ap.add_argument("--refresh", action="store_true", help="Ignore cache; re-fetch.")
    ap.add_argument("--offline", action="store_true",
                    help="Use the cache only; error if it is absent.")
    ap.add_argument("--report-dir", type=Path, default=None,
                    help="Also write biolink_drift_report.{md,json} to this scratch dir.")
    ap.add_argument("--emit-enum", type=Path, default=None,
                    help="Write a drift-ANNOTATED copy of the enum to this scratch path "
                         "(for a human-reviewed DRAFT PR). Never edits the committed schema.")
    ap.add_argument("--show-added", action="store_true",
                    help="List the Biolink predicates we don't use (large).")
    ap.add_argument("--json", action="store_true", help="Print machine-readable JSON to stdout.")
    ap.add_argument("--fail-on-drift", action="store_true",
                    help="Exit 1 if any removed/renamed/deprecated predicate is found.")
    args = ap.parse_args()

    url = args.biolink_url or BIOLINK_RAW.format(ref=args.biolink_ref)

    # Guard cardinal rule #1: never write over the committed schema/polarity file.
    if args.emit_enum is not None:
        target = args.emit_enum.resolve()
        if target in {SCHEMA.resolve(), POLARITY.resolve()}:
            print("refusing to write --emit-enum over a committed source file "
                  f"({target}). Choose a scratch path.", file=sys.stderr)
            return 2

    try:
        bl_text = fetch_biolink_yaml(url, args.cache, refresh=args.refresh, offline=args.offline)
        bl = yaml.safe_load(bl_text)
    except Exception as exc:  # noqa: BLE001 — surface any fetch/parse failure cleanly
        print(f"error obtaining Biolink model: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    our_enum = load_our_enum()
    polarity = load_polarity()
    bl_pred_names, bl_curies, bl_deprecated = biolink_predicates(bl)

    drift = compute_drift(our_enum, polarity, bl_pred_names, bl_curies, bl_deprecated)
    meta = {
        "biolink_url": url,
        "biolink_version": bl.get("version", "unknown"),
        "biolink_predicate_count": len(bl_pred_names),
        "our_enum_size": len(our_enum),
        "polarity_size": len(polarity),
    }

    if args.json:
        print(json.dumps({"meta": meta, "drift": drift}, indent=2))
    else:
        print(render_report(drift, meta, show_added=args.show_added))

    if args.report_dir is not None:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        (args.report_dir / "biolink_drift_report.md").write_text(
            render_report(drift, meta, show_added=True)
        )
        (args.report_dir / "biolink_drift_report.json").write_text(
            json.dumps({"meta": meta, "drift": drift}, indent=2)
        )
        print(f"\nWrote report to {args.report_dir}/biolink_drift_report.{{md,json}}",
              file=sys.stderr)

    if args.emit_enum is not None:
        args.emit_enum.parent.mkdir(parents=True, exist_ok=True)
        args.emit_enum.write_text(emit_annotated_enum(drift, meta))
        print(f"Wrote drift-annotated DRAFT enum to {args.emit_enum} "
              f"(review required; not applied).", file=sys.stderr)

    has_drift = bool(drift["removed"] or drift["renamed"] or drift["deprecated"])
    if args.fail_on_drift and has_drift:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
