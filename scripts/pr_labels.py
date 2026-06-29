"""
Derive PR scenario labels for a curated path, from machine signals only.

`/create-pr` uses this to tailor each PR to its outcome (clean vs needs-review,
full-text-sourced or not). It reads two committed artifacts:

  - the path record           kb/paths/<id>.yaml      (NO_EVIDENCE edges, source_tier)
  - the critic sidecar        provenance/<id>.semantic_review.yaml  (overall_verdict)

Content labels emitted (definitions in .github/labels.yml):
  - ai-curated         critic ACCEPT and no NO_EVIDENCE edge — clean, auto-merge candidate
  - needs-human-review critic ESCALATE/ABSTAIN, no critic sidecar, or any NO_EVIDENCE edge
  - full-text-sourced  >=1 EvidenceItem has source_tier FULL_TEXT (snippet body now stripped,
                       so it is not CI-verbatim-checkable — reviewer may want to spot-check)

The `backfill` / `new-path` label is added by /create-pr from git context (modified vs
added file), not here — this script only reads the record's own content.

Usage:
    python scripts/pr_labels.py kb/paths/<file>.yaml          # space-separated labels
    python scripts/pr_labels.py <file> --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
PROVENANCE_DIR = REPO / "provenance"


def _sidecar_for(record_id: str) -> dict | None:
    p = PROVENANCE_DIR / f"{record_id}.semantic_review.yaml"
    if not p.exists():
        return None
    try:
        return yaml.safe_load(p.read_text()) or {}
    except Exception:
        return None


def labels_for(path_file: str) -> list[str]:
    doc = yaml.safe_load(Path(path_file).read_text()) or {}
    record_id = (doc.get("graph") or {}).get("_id") or Path(path_file).stem

    has_no_evidence = False
    full_text_sourced = False
    for link in doc.get("links") or []:
        for ev in (link.get("evidence") or []):
            if (ev.get("supports") or "").upper() == "NO_EVIDENCE":
                has_no_evidence = True
            if (ev.get("source_tier") or "").upper() == "FULL_TEXT":
                full_text_sourced = True

    sidecar = _sidecar_for(record_id)
    verdict = (sidecar or {}).get("overall_verdict")

    labels: list[str] = []
    # A path is "ai-curated" (clean / auto-merge candidate) only when the critic
    # explicitly ACCEPTed it AND it carries no held-back edges. Anything else — an
    # escalation verdict, a NO_EVIDENCE edge, or no critic run at all — needs a human.
    if verdict == "ACCEPT" and not has_no_evidence:
        labels.append("ai-curated")
    else:
        labels.append("needs-human-review")

    if full_text_sourced:
        labels.append("full-text-sourced")

    return labels


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path_file", help="kb/paths/<file>.yaml")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    labels = labels_for(args.path_file)
    if args.json:
        print(json.dumps(labels))
    else:
        print(" ".join(labels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
