# The DrugMechDB pipeline — setup, curate → validate → publish

This document describes how to reproduce the environment and run the full pipeline end
to end: from a fresh clone, through curating and validating a record, to regenerating
the published artifacts.

The **per-record files under `kb/paths/`** are the source of truth. The consolidated
`indication_paths.{yaml,json}` monoliths and `kb/paths/_index.yaml` are **generated**
from them — never hand-edited.

---

## 1. Environment (reproducible)

Python **3.10** (developed and locked against 3.10.11). The virtualenv lives at
`.venv-py310/` and is git-ignored.

**Exact, reproducible install** — pinned to the locked dependency set:

```bash
python3.10 -m venv .venv-py310
.venv-py310/bin/pip install -r requirements.lock   # 152 pinned deps (frozen, pip-check clean)
.venv-py310/bin/pip install -e . --no-deps          # install this package, don't disturb the pins
```

**Loose install** (latest compatible deps, for development):

```bash
.venv-py310/bin/pip install -e ".[dev,judge]"
```

- `requirements.lock` is the exact pin (regenerate with `pip freeze`); `pyproject.toml`
  holds the loose lower-bound spec. Use the lock for reproducible/CI installs.
- Extras: `dev` (linkml, pytest, oaklib), `judge` (anthropic, openai — only needed for the
  live semantic critic; the pipeline otherwise runs without them).

Sanity check: `just env-info` and `python scripts/qc.py --help`.

---

## 2. Curate → validate → publish

### Stage 1 — Curate a record
Curation is driven by the `/curate <Drug> for <Disease>` command (see
`.claude/commands/curate.md` for the full workflow). It resolves identifiers, finds and
caches PubMed evidence, drafts one connected `Drug → … → Disease` chain, and writes a
single file to `kb/paths/{drugbank}_{disease_mesh}_{n}.yaml`. Evidence snippets must be a
**verbatim** substring of a fetched reference (`scripts/pubmed_fetch.py`).

### Stage 2 — Canonicalize predicates
```bash
python scripts/canonicalize_predicates.py --write kb/paths/<file>.yaml   # or: just canonicalize-write
```
Lowercases, strips `biolink:` prefixes, turns underscores into spaces. Idempotent.

### Stage 3 — The QC gate (the source of truth for "is this record valid")
```bash
just qc kb/paths/<file>.yaml            # auto profile
just qc                                  # whole corpus
just qc-layer 2 kb/paths/<file>.yaml     # isolate one layer
```
Profiles and layers:

| Profile | When | Layers |
|---|---|---|
| `legacy` | no per-edge evidence | 1, 2, 3 |
| `ai_curated` | any edge has `evidence:` | 1, 2, 3, 4 |

1. **schema** (LinkML `MechanisticPath`) · 2. **node ontology** (CURIE prefix ↔ label, plus
the invisible/whitespace-character guard on ids and names) · 3. **predicate enum** (67
Biolink predicates) · 4. **reference** (every snippet is verbatim in its cached source).

Exit codes: `0` pass · `1` fail · `2` no files. The pre-edit hook
(`.claude/hooks/validate_path_hook.py`) runs the gate `--offline` **before** any write to
`kb/paths/*.yaml` lands and blocks invalid writes.

### Stage 4 — Semantic critic (after the QC gate passes)
```bash
python scripts/quality/critic.py kb/paths/<file>.yaml --round 1 --max-rounds 3
```
An independent, grounded reviewer that re-derives each edge's support and judges the chain.
Verdict ∈ `ACCEPT` / `RE_CURATE` / `ESCALATE` / `ABSTAIN`; on `RE_CURATE` it prints flagged
edges (the problem, never the fix) and you loop back to Stage 1. Its audit is written to
`provenance/<id>.semantic_review.yaml`. (Deterministic structural signals — polarity,
short-circuit, type checks — are reported by `scripts/quality/structural_quality.py`.)

### Stage 5 — Publish / consolidate
Regenerate the consolidated artifacts from the per-record source of truth:
```bash
python scripts/rebuild_monolith.py           # indication_paths.{yaml,json}
python scripts/rebuild_monolith.py --check    # CI: exit 1 if the artifacts have drifted
just rebuild-index                            # kb/paths/_index.yaml
```
(The inverse, monolith → per-record, is `scripts/split_monolith.py`.)

---

## 3. Data-hygiene & maintenance tools

```bash
python scripts/detect_duplicates.py           # exact / near-duplicate records (report-only)
python scripts/validate_node_ontology.py       # Layer 2 standalone (prefix + character guards)
```

---

## 4. Reproducibility checklist

- Pin: `requirements.lock` (regenerate: `.venv-py310/bin/pip freeze | grep -viE '^-e |drugmechdb'`).
- Verify env: `pip check` (should report no broken requirements).
- Verify published artifacts are current: `python scripts/rebuild_monolith.py --check`.
- Re-run the gate exactly as CI does before opening a PR: `just qc`.
