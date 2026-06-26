"""
Phase 1: Layer-1 schema validation of every file in kb/paths/.

Compiles the LinkML schema once to JSON Schema, then validates each
kb/paths/*.yaml against it and aggregates failures by message pattern.

Outputs:
  - docs/phase1_validation_report.md       (human report)
  - docs/phase1_validation_failures.json   (machine-readable per-file failures)

Usage:
    python scripts/phase1_validate_all.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from jsonschema import Draft7Validator
from linkml.generators.jsonschemagen import JsonSchemaGenerator

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "src" / "drugmechdb" / "schema" / "drugmechdb.yaml"
PATHS_DIR = REPO / "kb" / "paths"
REPORT = REPO / "docs" / "phase1_validation_summary.md"
FAILURES = REPO / "docs" / "phase1_validation_failures.json"


def compile_schema() -> dict:
    gen = JsonSchemaGenerator(str(SCHEMA), top_class="MechanisticPath")
    return json.loads(gen.serialize())


def normalize_error(msg: str) -> str:
    """Group similar errors by stripping variable parts."""
    # Strip concrete strings/dicts inside the message
    msg = re.sub(r"'[^']{20,}'", "'<…>'", msg)
    msg = re.sub(r"\{[^{}]+\}", "{<…>}", msg)
    msg = re.sub(r"PMID:\d+", "PMID:<n>", msg)
    msg = re.sub(r"\d{4,}", "<n>", msg)
    return msg.strip()


def main() -> int:
    if not SCHEMA.exists():
        print(f"ERROR: schema not found at {SCHEMA}", file=sys.stderr)
        return 2

    print(f"Compiling schema: {SCHEMA}")
    js = compile_schema()
    validator = Draft7Validator(js)

    files = sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    print(f"Validating {len(files)} files against MechanisticPath…")

    per_file: dict[str, list[str]] = {}
    error_buckets: Counter[str] = Counter()
    bucket_examples: dict[str, list[str]] = defaultdict(list)
    bucket_files: dict[str, set[str]] = defaultdict(set)
    pass_count = 0
    fail_count = 0

    for i, path in enumerate(files, start=1):
        if i % 500 == 0:
            print(f"  …{i}/{len(files)}")
        try:
            with path.open() as fh:
                doc = yaml.safe_load(fh)
        except Exception as e:
            per_file[path.name] = [f"YAML_PARSE_ERROR: {e}"]
            error_buckets["YAML_PARSE_ERROR"] += 1
            bucket_files["YAML_PARSE_ERROR"].add(path.name)
            fail_count += 1
            continue

        errors = list(validator.iter_errors(doc))
        if not errors:
            pass_count += 1
            continue

        fail_count += 1
        msgs = []
        for err in errors:
            location = "/".join(str(p) for p in err.absolute_path) or "/"
            raw = f"[{location}] {err.message}"
            msgs.append(raw)
            bucket = normalize_error(err.message)
            error_buckets[bucket] += 1
            bucket_files[bucket].add(path.name)
            if len(bucket_examples[bucket]) < 3:
                bucket_examples[bucket].append(f"{path.name}: {raw}")
        per_file[path.name] = msgs

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    FAILURES.write_text(
        json.dumps(
            {
                "total_files": len(files),
                "pass": pass_count,
                "fail": fail_count,
                "per_file": per_file,
                "error_buckets": {
                    k: {
                        "count": v,
                        "files_affected": len(bucket_files[k]),
                        "examples": bucket_examples[k],
                    }
                    for k, v in error_buckets.most_common()
                },
            },
            indent=2,
        )
    )

    lines = []
    lines.append("# Phase 1 Validation Report\n")
    lines.append(f"Schema: `src/drugmechdb/schema/drugmechdb.yaml` (class `MechanisticPath`)\n")
    lines.append(f"Files validated: **{len(files)}**\n")
    lines.append(f"- Pass: **{pass_count}** ({pass_count / len(files):.1%})")
    lines.append(f"- Fail: **{fail_count}** ({fail_count / len(files):.1%})\n")
    lines.append("## Failure buckets (most common first)\n")
    lines.append("| # | Files affected | Total occurrences | Normalized error |")
    lines.append("|---|---|---|---|")
    for idx, (bucket, count) in enumerate(error_buckets.most_common(), 1):
        # Escape pipes in markdown
        b = bucket.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {idx} | {len(bucket_files[bucket])} | {count} | `{b}` |"
        )
    lines.append("\n## Examples per bucket\n")
    for bucket, _ in error_buckets.most_common():
        lines.append(f"### `{bucket}`")
        for ex in bucket_examples[bucket]:
            lines.append(f"- `{ex}`")
        lines.append("")

    REPORT.write_text("\n".join(lines))
    print(f"\nPass: {pass_count} / {len(files)}")
    print(f"Fail: {fail_count} / {len(files)}")
    print(f"Report: {REPORT}")
    print(f"Failures JSON: {FAILURES}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
