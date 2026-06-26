#!/usr/bin/env python3
"""
Pre-edit validation hook for DrugMechDB path records.

This is the "self-validating KB" property ported from Dismech
(.claude/hooks/validate_disorder_hook.py). It runs as a PreToolUse hook on
Edit / Write / MultiEdit and BLOCKS any change that would leave a
`kb/paths/*.yaml` record failing QC — *before* the write lands on disk.

How it works
------------
1. Claude Code pipes a JSON object on stdin describing the pending tool call
   ({"tool_name": ..., "tool_input": {...}}).
2. We only care about Write/Edit/MultiEdit targeting kb/paths/*.yaml
   (the per-record path files). Everything else is allowed (exit 0).
3. We *simulate* the post-edit content in memory (apply the Edit/MultiEdit to
   the current file, or take the Write payload verbatim).
4. We write the simulated result to a temp file and run the real QC gate
   (scripts/qc.py, auto-profile, --offline) against it.
5. If QC fails we print the report to stderr and exit 2, which tells Claude
   Code to BLOCK the tool call. Otherwise exit 0 and the edit proceeds.

Design choices (vs. Dismech)
-----------------------------
- Calls `scripts/qc.py` (this repository's 4-layer orchestrator) instead of Dismech's
  `just validate`. qc.py auto-detects the legacy/ai_curated profile per file,
  so a half-finished legacy edit is held to Layers 1-3 and an evidence-bearing
  edit to all four.
- Runs Layer 4 with `--offline`: a pre-edit hook must be fast and deterministic,
  so snippets are checked against the committed references_cache/ rather than
  hitting PubMed on every keystroke. (Fetch PMIDs into the cache first via
  scripts/pubmed_fetch.py.)
- FAIL-OPEN when the environment isn't bootstrapped. .venv-py310 is gitignored
  and may be absent on a fresh clone; rather than block *every* edit in that
  state, we print a loud warning and allow the edit. The hook only enforces
  once the venv exists. (Better: a missing env is an obvious, visible warning;
  a hard block on infra would just train people to disable the hook.)
- _index.yaml is skipped — it is a generated aggregate, not a record, and would
  not pass the per-record schema.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Repo root = three levels up from this file (.claude/hooks/<this>).
REPO = Path(__file__).resolve().parent.parent.parent
VENV_PY = REPO / ".venv-py310" / "bin" / "python"
QC_SCRIPT = REPO / "scripts" / "qc.py"

# Only records under this directory are gated.
PATHS_MARKER = "kb/paths"

# references_cache/ is script-write-only — see the fence in main().
CACHE_MARKER = "references_cache"


def simulate_edit(file_path: Path, old_string: str, new_string: str) -> str | None:
    """Return the file content after an Edit, or None if it can't be simulated."""
    if not file_path.exists():
        # Editing a non-existent file is Claude Code's error to report, not ours.
        return None
    content = file_path.read_text()
    if old_string not in content:
        # Same: let the real tool surface the "old_string not found" error.
        return None
    return content.replace(old_string, new_string, 1)


def simulate_multi_edit(file_path: Path, edits: list) -> str | None:
    """Return the file content after a MultiEdit, applying edits in order."""
    if not file_path.exists():
        return None
    content = file_path.read_text()
    for edit in edits:
        old_string = edit.get("old_string", "")
        new_string = edit.get("new_string", "")
        if old_string and old_string in content:
            content = content.replace(old_string, new_string, 1)
    return content


def run_qc(content: str, original_path: Path) -> tuple[bool, str]:
    """Write simulated content to a temp file and run the QC gate against it.

    Returns (passed, combined_output).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Keep the original filename so profile/_id-derived checks behave the same.
        temp_path = Path(tmpdir) / original_path.name
        temp_path.write_text(content)
        cmd = [
            str(VENV_PY),
            str(QC_SCRIPT),
            "--offline",          # deterministic Layer 4: cache-only, no PubMed fetch
            str(temp_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
        output = proc.stdout + proc.stderr
        # qc.py: 0 = all layers pass, 1 = a layer failed, 2 = no files found.
        # Block only on a genuine validation failure (1). Treat 2/other as an
        # infrastructure hiccup and fail-open with the output visible.
        if proc.returncode == 1:
            return False, output
        return True, output


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # No parseable input — nothing to gate.
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    file_path_str = tool_input.get("file_path", "")
    if not file_path_str:
        sys.exit(0)

    file_path = Path(file_path_str)

    # Hard fence: references_cache/ is script-write-only (scripts/pubmed_fetch.py).
    # The agent must never author or alter the source text that Layer 4 trusts —
    # otherwise a hallucinated snippet could "match" a fabricated source. The
    # fetch script writes the cache via the filesystem, not via Edit/Write, so it
    # is unaffected by this block. (Placed before the venv check so the fence
    # holds even on an un-bootstrapped clone.)
    if CACHE_MARKER in str(file_path):
        print("=" * 64, file=sys.stderr)
        print("BLOCKED: references_cache/ is script-write-only.", file=sys.stderr)
        print(f"  file: {file_path}", file=sys.stderr)
        print("Populate it with:", file=sys.stderr)
        print("  python scripts/pubmed_fetch.py fetch [--fulltext] PMID:x", file=sys.stderr)
        print("Do not hand-edit cached references — Layer 4's verbatim-snippet", file=sys.stderr)
        print("check depends on their integrity.", file=sys.stderr)
        print("=" * 64, file=sys.stderr)
        sys.exit(2)

    # Only gate per-record path files; skip the generated index.
    if PATHS_MARKER not in str(file_path) or file_path.suffix != ".yaml":
        sys.exit(0)
    if file_path.name == "_index.yaml":
        sys.exit(0)

    # Fail-open if the env isn't bootstrapped (see module docstring).
    if not VENV_PY.exists():
        print(
            "[validate_path_hook] .venv-py310 not found — skipping pre-edit QC. "
            "Bootstrap with `pip install -e \".[dev]\"` to enable the validation gate.",
            file=sys.stderr,
        )
        sys.exit(0)

    # Build the simulated post-edit content.
    if tool_name == "Write":
        new_content = tool_input.get("content", "")
    elif tool_name == "Edit":
        new_content = simulate_edit(
            file_path,
            tool_input.get("old_string", ""),
            tool_input.get("new_string", ""),
        )
    else:  # MultiEdit
        new_content = simulate_multi_edit(file_path, tool_input.get("edits", []))

    if new_content is None:
        # Couldn't simulate (missing file / unmatched old_string) — let the real
        # tool report that; we don't block.
        sys.exit(0)

    passed, output = run_qc(new_content, file_path)

    if not passed:
        print("=" * 64, file=sys.stderr)
        print("BLOCKED: this edit would leave the path record failing QC.", file=sys.stderr)
        print(f"  file: {file_path}", file=sys.stderr)
        print("=" * 64, file=sys.stderr)
        print(output.rstrip(), file=sys.stderr)
        print("=" * 64, file=sys.stderr)
        print("Fix the issues above, then retry the edit. (Run `just qc " +
              f"{file_path}` to reproduce.)", file=sys.stderr)
        sys.exit(2)  # exit code 2 => Claude Code blocks the tool call

    print(f"[validate_path_hook] QC passed for {file_path.name} — allowing edit.",
          file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
