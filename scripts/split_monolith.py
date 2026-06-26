"""
Split indication_paths.yaml into individual per-path YAML files under kb/paths/.

Usage:
    python3 scripts/split_monolith.py [--dry-run]

Output:
    kb/paths/<_id>.yaml   — one file per mechanistic path
    kb/paths/_index.yaml  — maps _id -> filename + graph metadata
"""

import argparse
import sys
from pathlib import Path

import yaml


# Preserve insertion order and avoid aliases in output
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


def load_source(source_path: Path) -> list:
    with source_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{source_path} did not parse as a YAML list")
    return data


def derive_filename(entry: dict, index: int) -> str:
    """Return the filename stem for an entry, falling back to positional index."""
    graph = entry.get("graph", {})
    id_ = graph.get("_id")
    if id_:
        # Sanitise: replace characters unsafe for filenames
        safe = id_.replace(":", "_").replace("/", "_").replace(" ", "_")
        return safe
    # Fallback: construct from drugbank + disease_mesh
    drugbank = graph.get("drugbank", "").replace(":", "").replace("/", "")
    disease = graph.get("disease_mesh", "").replace(":", "_")
    if drugbank and disease:
        return f"{drugbank}_{disease}_{index}"
    return f"path_{index:05d}"


def build_index(entries: list, filenames: list[str]) -> list:
    index = []
    for entry, fname in zip(entries, filenames):
        graph = entry.get("graph", {})
        index.append(
            {
                "id": graph.get("_id", fname),
                "file": f"{fname}.yaml",
                "drug": graph.get("drug"),
                "drug_mesh": graph.get("drug_mesh"),
                "drugbank": graph.get("drugbank"),
                "disease": graph.get("disease"),
                "disease_mesh": graph.get("disease_mesh"),
            }
        )
    return index


def split(source_path: Path, out_dir: Path, dry_run: bool = False) -> None:
    print(f"Loading {source_path} …")
    entries = load_source(source_path)
    print(f"  {len(entries)} paths found")

    out_dir.mkdir(parents=True, exist_ok=True)

    filenames: list[str] = []
    seen: set[str] = set()
    collisions = 0

    for i, entry in enumerate(entries):
        fname = derive_filename(entry, i)
        if fname in seen:
            fname = f"{fname}_dup{i}"
            collisions += 1
        seen.add(fname)
        filenames.append(fname)

    if collisions:
        print(f"  WARNING: {collisions} filename collision(s) resolved with _dup suffix")

    # Write individual files
    written = 0
    for entry, fname in zip(entries, filenames):
        out_path = out_dir / f"{fname}.yaml"
        if not dry_run:
            with out_path.open("w", encoding="utf-8") as fh:
                dump_yaml(entry, fh)
        written += 1

    # Write index
    index = build_index(entries, filenames)
    index_path = out_dir / "_index.yaml"
    if not dry_run:
        with index_path.open("w", encoding="utf-8") as fh:
            dump_yaml(index, fh)

    # Report
    print(f"\n{'DRY RUN — ' if dry_run else ''}Results:")
    print(f"  Source paths   : {len(entries)}")
    print(f"  Files written  : {written}")
    print(f"  Index entries  : {len(index)}")
    print(f"  Output dir     : {out_dir}")
    print(f"  Index file     : {index_path}")
    if collisions:
        print(f"  Collisions     : {collisions} (resolved)")
    else:
        print(f"  Collisions     : 0")

    if len(entries) != written:
        print(f"\n  ERROR: count mismatch — {len(entries)} in vs {written} out", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\n  OK: all {len(entries)} paths accounted for")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="indication_paths.yaml",
        help="Path to the monolithic YAML file (default: indication_paths.yaml)",
    )
    parser.add_argument(
        "--out-dir",
        default="kb/paths",
        help="Output directory for individual path files (default: kb/paths)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing any files",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    source_path = (repo_root / args.source).resolve()
    out_dir = (repo_root / args.out_dir).resolve()

    if not source_path.exists():
        print(f"ERROR: source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    split(source_path, out_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
