# Contributing

There are two kinds of contribution, and they follow different rules: **records**
(a drug→disease mechanism path under `kb/paths/`) and **code** (the validators,
curation harness, and tooling under `scripts/`, `src/`, and `tests/`).

Set up the environment first — see **Getting started** in the `README.md`.

## Contributing a record

The rules for what a record may contain live in **`AGENTS.md`** (the contract) and
**`CurationGuide.md`** (the detailed guide). In short: curate only established,
already-asserted mechanisms; every edge carries evidence whose snippet is a verbatim
substring of a source you fetched; no predicted mechanism is ever an input.

1. **Curate** with `/curate <Drug> for <Disease>` in Claude Code, or by hand following
   `AGENTS.md`. The pre-edit hook validates every write to `kb/paths/` before it lands.
2. **Pass the semantic critic** (`scripts/quality/critic.py`), which records its audit in
   `provenance/<_id>.semantic_review.yaml`.
3. **Strip full text** — `python scripts/pubmed_fetch.py strip-fulltext --all`. Full-text
   bodies are used only to verify snippets and are never committed; CI rejects any PR that
   still carries one.
4. **Re-validate exactly as CI will** — QC Layers 1–3 plus the structural invariants
   (connectivity, no cycles, no duplicate edges, no drug→disease shortcut):
   `python scripts/quality/gate.py kb/paths/<your-record>.yaml --no-critic --no-verbatim`
5. **Open one PR per drug–disease path** where practical, from a feature branch. Stage only
   the record, the `references_cache/` files it cites, and its `provenance/` sidecar — never
   `git add -A`. `/create-pr` automates steps 3–5.

Never hand-edit generated files: `kb/paths/_index.yaml` and the `indication_paths.*`
monoliths are rebuilt by `scripts/rebuild_monolith.py` and `just rebuild-index`.

## Contributing code

- **Tests pass:** `just test` (or `.venv-py310/bin/python -m pytest tests/`). New behaviour
  comes with a test; tests run offline and never call a paid API — use the stub backends.
- **The QC gate stays the single source of truth** for record validity. A change to what
  counts as valid belongs in `scripts/qc.py` and its layers, not in a downstream tool.
- **Reports use repo-relative paths**, never absolute ones, so a run never records the
  contributor's home directory.
- **No internal or personal content** in tracked files — this is a public repository.
- **Dependencies:** add one only to close a demonstrated gap, and update both
  `pyproject.toml` and `requirements.lock`.

## Reporting a problem

Open an issue. For a record, name the `_id` and the layer or criterion it fails; for a
bug, include the command you ran and its output.
