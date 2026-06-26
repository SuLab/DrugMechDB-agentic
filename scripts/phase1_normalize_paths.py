"""
Phase 1: idempotent normalization of legacy field names in kb/paths/*.yaml.

Brings each path file in line with the canonical slot names declared in
src/drugmechdb/schema/drugmechdb.yaml so that linkml-validate passes under
the `legacy` profile.

Top-level normalizations:
  - reference   -> references  (rename; ensure list; split whitespace-joined URL strings)
  - comments    -> comment     (single string; multiple values are newline-joined)
  - commments   -> comment     (misspelling)
  - comemnt     -> comment     (misspelling)
  - drugbank: null -> field removed (now optional in schema)

Per-node normalizations:
  - alt_name    -> alt_names   (rename; ensure list)
  - alt-name    -> alt_names   (rename; ensure list)
  - all_id      -> alt_ids     (rename; ensure list)
  - alt_ids: <scalar> -> alt_ids: [<scalar>]
  - reference: <url>  -> promoted to top-level `references` list; field dropped from node

Idempotency: re-running the script after a successful pass is a no-op.

Usage:
    python scripts/phase1_normalize_paths.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"


class _IndentDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, indentless=False)


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_IndentDumper.add_representer(str, _str_representer)


def dump_yaml(data, stream=None):
    return yaml.dump(
        data,
        stream=stream,
        Dumper=_IndentDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def _as_list(value: Any) -> list:
    """Coerce a scalar / string into a list, splitting whitespace-joined strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Split on whitespace only when the string contains spaces (URL-list case)
        if " " in value.strip() and value.strip().startswith(("http://", "https://")):
            return [tok for tok in value.split() if tok]
        return [value]
    return [value]


def normalize_node(node: dict, promoted_refs: list[str]) -> tuple[dict, list[str]]:
    """Return (new_node, list-of-change-descriptions)."""
    changes: list[str] = []
    out: dict = {}

    # Preserve insertion order while doing renames
    rename_map_alt_names = ("alt_name", "alt-name")
    rename_map_alt_ids = ("all_id",)

    for k, v in node.items():
        if k in rename_map_alt_names:
            existing = out.get("alt_names", [])
            existing.extend(_as_list(v))
            out["alt_names"] = existing
            changes.append(f"node: {k} -> alt_names")
        elif k in rename_map_alt_ids:
            existing = out.get("alt_ids", [])
            existing.extend(_as_list(v))
            out["alt_ids"] = existing
            changes.append(f"node: {k} -> alt_ids")
        elif k == "alt_ids":
            existing = out.get("alt_ids", [])
            existing.extend(_as_list(v))
            out["alt_ids"] = existing
            if not isinstance(v, list):
                changes.append("node: alt_ids scalar -> list")
        elif k == "alt_names":
            existing = out.get("alt_names", [])
            existing.extend(_as_list(v))
            out["alt_names"] = existing
            if not isinstance(v, list):
                changes.append("node: alt_names scalar -> list")
        elif k == "reference":
            # Promote node-level reference to top-level references; drop from node.
            for url in _as_list(v):
                promoted_refs.append(url)
            changes.append("node: reference promoted to top-level references")
        else:
            out[k] = v

    return out, changes


def normalize_doc(doc: dict) -> tuple[dict, list[str]]:
    changes: list[str] = []
    promoted_refs: list[str] = []

    # Per-node normalization (we mutate doc['nodes'] in place)
    if isinstance(doc.get("nodes"), list):
        new_nodes = []
        for node in doc["nodes"]:
            if isinstance(node, dict):
                new_node, node_changes = normalize_node(node, promoted_refs)
                new_nodes.append(new_node)
                changes.extend(node_changes)
            else:
                new_nodes.append(node)
        doc["nodes"] = new_nodes

    # Top-level renames: reference -> references
    if "reference" in doc:
        existing = doc.get("references")
        existing_list = _as_list(existing) if existing is not None else []
        existing_list.extend(_as_list(doc["reference"]))
        doc["references"] = existing_list
        del doc["reference"]
        changes.append("top: reference -> references")

    # Top-level renames: comments / misspellings -> comment
    for legacy_key in ("comments", "commments", "comemnt"):
        if legacy_key in doc:
            existing = doc.get("comment")
            value = doc[legacy_key]
            if isinstance(value, list):
                joined = "\n".join(str(v) for v in value if v is not None)
            else:
                joined = str(value) if value is not None else ""
            if existing:
                doc["comment"] = str(existing) + "\n" + joined
            else:
                doc["comment"] = joined
            del doc[legacy_key]
            changes.append(f"top: {legacy_key} -> comment")

    # Promoted references from node level
    if promoted_refs:
        existing = doc.get("references")
        existing_list = _as_list(existing) if existing is not None else []
        existing_list.extend(promoted_refs)
        doc["references"] = existing_list

    # Coerce top-level references scalar to list (and split whitespace)
    if "references" in doc:
        before = doc["references"]
        after = _as_list(before)
        if before != after:
            doc["references"] = after
            changes.append("top: references coerced to list")

    # Drop graph identifier fields that are explicitly null (now optional).
    # The schema treats absent and null differently for JSON-Schema validation;
    # absent is what we want.
    # Also strip literal "MESH:null" placeholders left by past curation
    # (10 files, all on drug_mesh).
    graph = doc.get("graph")
    if isinstance(graph, dict):
        for null_key in ("drugbank", "drug_mesh"):
            value = graph.get(null_key)
            if null_key in graph and (
                value is None
                or (isinstance(value, str) and value.strip().lower() in ("mesh:null", "db:null"))
            ):
                del graph[null_key]
                if value is None:
                    changes.append(f"graph: {null_key} null -> removed")
                else:
                    changes.append(f"graph: {null_key} '{value}' placeholder -> removed")

    return doc, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument(
        "--paths-dir",
        default=str(PATHS_DIR),
        help=f"Directory of per-path YAML files (default: {PATHS_DIR})",
    )
    args = parser.parse_args()

    paths_dir = Path(args.paths_dir).resolve()
    files = sorted(p for p in paths_dir.glob("*.yaml") if p.name != "_index.yaml")
    print(f"Normalizing {len(files)} files under {paths_dir} (dry-run={args.dry_run})")

    change_counts: Counter[str] = Counter()
    files_touched = 0

    for i, path in enumerate(files, start=1):
        if i % 500 == 0:
            print(f"  …{i}/{len(files)}")
        with path.open() as fh:
            doc = yaml.safe_load(fh)
        if not isinstance(doc, dict):
            continue

        new_doc, changes = normalize_doc(doc)
        if changes:
            files_touched += 1
            for c in changes:
                change_counts[c] += 1
            if not args.dry_run:
                with path.open("w", encoding="utf-8") as fh:
                    dump_yaml(new_doc, fh)

    print()
    print(f"Files touched: {files_touched} / {len(files)}")
    print("Change-type counts:")
    for change, count in change_counts.most_common():
        print(f"  {count:6d}  {change}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
