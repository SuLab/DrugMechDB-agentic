"""
Layer 1 — LinkML schema validation for one or more path files.

Compiles src/drugmechdb/schema/drugmechdb.yaml to JSON Schema (top class:
MechanisticPath) and validates each input file against it.

Usage:
    python scripts/validate_schema.py                 # all files in kb/paths/
    python scripts/validate_schema.py kb/paths/X.yaml # specific file(s)
    python scripts/validate_schema.py --json          # machine-readable output

Exit status: 0 if every file is structurally valid, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml
from jsonschema import Draft7Validator
from linkml.generators.jsonschemagen import JsonSchemaGenerator

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "src" / "drugmechdb" / "schema" / "drugmechdb.yaml"
PATHS_DIR = REPO / "kb" / "paths"


@lru_cache(maxsize=1)
def _validator() -> Draft7Validator:
    gen = JsonSchemaGenerator(str(SCHEMA), top_class="MechanisticPath")
    return Draft7Validator(json.loads(gen.serialize()))


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
        else:
            print(f"warning: {t} is not a file or directory", file=sys.stderr)
    return files


def validate_file(path: Path) -> list[dict]:
    try:
        with path.open() as fh:
            doc = yaml.safe_load(fh)
    except Exception as e:
        return [{"file": str(path), "location": "/", "message": f"YAML parse error: {e}"}]

    v = _validator()
    failures = []
    for err in v.iter_errors(doc):
        location = "/".join(str(p) for p in err.absolute_path) or "/"
        failures.append({"file": str(path), "location": location, "message": err.message})
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", help="Files or directories. Default: kb/paths/")
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args()

    files = iter_files(args.targets)
    all_failures = []
    for path in files:
        all_failures.extend(validate_file(path))

    summary = {
        "files_checked": len(files),
        "failure_count": len(all_failures),
        "files_failing": len({f["file"] for f in all_failures}),
        "failures": all_failures,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        if all_failures:
            print(f"Layer 1 FAIL: {summary['failure_count']} structural errors across {summary['files_failing']} files")
            for f in all_failures[:30]:
                print(f"  {Path(f['file']).name}: [{f['location']}] {f['message'][:140]}")
            if len(all_failures) > 30:
                print(f"  …and {len(all_failures) - 30} more (use --json for full list)")
        else:
            print(f"Layer 1 PASS: {len(files)} files pass LinkML schema validation.")
    return 0 if not all_failures else 1


if __name__ == "__main__":
    sys.exit(main())
