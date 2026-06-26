# Phase 2 Report — Validation Tooling

**PRD reference:** [PRD v3 §6 Phase 2](PRD_v3.md)
**Date:** May 2026
**Status:** Complete — all exit criteria met

## Exit criteria (PRD v3 §6 Phase 2)

> `just qc` runs all four layers locally with clear pass/fail output and honors the profile selector. **Layer 3 passes for 100% of legacy files.**

- ✅ All four layers run via `just qc` / `python scripts/qc.py`.
- ✅ Profile selector (`legacy` / `ai_curated` / `auto`) implemented and exercised by the pytest suite.
- ✅ Layer 3 passes for 4,846 / 4,846 legacy files (100%).

Layer 2 surfaces 230 real prefix violations and 1,768 tolerated legacy-prefix warnings in the corpus — captured in [phase2_gap_report.md](phase2_gap_report.md) for downstream remediation. Layer 4 is a no-op against legacy by design; end-to-end wiring is proven by `tests/fixtures/sample_ai_curated*.yaml` and 12 passing pytest cases.

## Layers

| Layer | Purpose | Implementation | Runs against |
|---|---|---|---|
| 1 | LinkML schema structural validation | [`scripts/validate_schema.py`](../scripts/validate_schema.py) | `legacy` + `ai_curated` |
| 2 | Node ID CURIE prefix matches Biolink label's canonical ontology | [`scripts/validate_node_ontology.py`](../scripts/validate_node_ontology.py) (`--deep` delegates to `linkml-term-validator`) | `legacy` + `ai_curated` |
| 3 | Every edge `key` ∈ `BiolinkPredicate` enum | [`scripts/validate_predicates.py`](../scripts/validate_predicates.py) | `legacy` + `ai_curated` |
| 4 | Every `snippet` is a verbatim substring of the cached PMID abstract | [`scripts/validate_references.py`](../scripts/validate_references.py) (wraps `linkml-reference-validator`) | `ai_curated` only |

## Profile selector

Per PRD §5.3.5:

| Profile | Layers | Evidence required | Auto-detection rule |
|---|---|---|---|
| `legacy` | 1, 2, 3 | No | File has no `evidence:` block on any edge |
| `ai_curated` | 1, 2, 3, 4 | Yes (≥1 per edge) | File has any `evidence:` block |

`scripts/qc.py --profile {auto,legacy,ai_curated}` controls selection; `auto` (default) groups files into buckets and applies the correct layer set per bucket in a single invocation.

The pytest suite exercises all three modes ([test_qc_auto_profile_legacy_for_corpus_sample](../tests/test_validation.py), [test_qc_auto_profile_ai_curated_for_fixture](../tests/test_validation.py), [test_qc_forced_legacy_skips_layer_4_on_ai_curated_file](../tests/test_validation.py)).

## Orchestrator and justfile

- [`scripts/qc.py`](../scripts/qc.py) — orchestrator. Shells out to each per-layer script with the right file set; aggregates exit codes; emits a summary table or JSON.
- [`justfile`](../justfile) — `just qc`, `just qc-legacy`, `just qc-ai`, `just qc-layer N`, `just qc-json`, `just test`. Also wraps Phase-1 / 1.5 maintenance helpers (`normalize`, `canonicalize`, `rebuild-index`) and an `env-info` target. Requires `just` (`brew install just`).

## Tooling installed

A second venv was created at `.venv-py310/` (Python 3.10.4) because `linkml-term-validator`, `linkml-reference-validator`, and modern `oaklib` require Python ≥ 3.10. Phase 1's `.venv` (Python 3.9) remains usable for the simpler scripts. Both venvs are excluded from version control via convention.

Key versions installed:

| Package | Version | Used by |
|---|---|---|
| `linkml` | 1.11.0 | Layer 1 (JSON Schema generation) |
| `linkml-runtime` | 1.11.0 | SchemaView for derived utilities |
| `linkml-term-validator` | 0.3.0 | Layer 2 deep mode (optional) |
| `linkml-reference-validator` | 0.1.8 | Layer 4 |
| `oaklib` | 0.6.23 | OAK adapters for `linkml-term-validator` deep mode |
| `pytest` | 9.0.3 | tests/ |
| `httpx`, `eutils`, `biopython` | latest | PubMed E-utilities (transitively used by `linkml-reference-validator`) |

## Schema changes

To wire Layer 4 cleanly, four small edits were made to [`src/drugmechdb/schema/drugmechdb.yaml`](../src/drugmechdb/schema/drugmechdb.yaml):

1. Added `oa:` and `dcterms:` prefixes to the schema's `prefixes:` block.
2. Tagged `snippet` slot with `slot_uri: oa:exact` (W3C Web Annotation excerpt URI — what `linkml-reference-validator` looks for to identify the supporting-text slot).
3. Tagged `reference` slot with `slot_uri: dcterms:references` (Dublin Core URI for citations).
4. Renamed slot `path_id` (alias `_id`) → `_id`. `linkml-reference-validator`'s slot-lookup didn't honor LinkML aliases; data files all already use `_id:`, so no data migration was required.

Layer 1 was re-validated after these changes: 4,846 / 4,846 still pass.

## Tests

`pytest tests/` — 12 cases, ~58 s on a typical laptop (most of the time is the Layer-1/2/3 runs against the full corpus).

| Test | Asserts |
|---|---|
| `test_layer1_legacy_corpus_passes` | 4,846 files pass schema validation |
| `test_layer1_ai_curated_fixture_passes` | Synthetic ai_curated path passes Layer 1 |
| `test_layer2_ai_curated_fixture_passes` | Synthetic ai_curated path passes Layer 2 |
| `test_layer2_legacy_corpus_has_known_gaps` | Legacy corpus has the 230 documented gaps |
| `test_layer3_legacy_corpus_passes_exit_criterion` | 4,846 files pass Layer 3 (the Phase 2 exit gate) |
| `test_layer3_ai_curated_fixture_passes` | Synthetic ai_curated path passes Layer 3 |
| `test_layer4_legacy_corpus_is_noop` | Legacy corpus has no evidence; Layer 4 is no-op |
| `test_layer4_ai_curated_fixture_passes_with_cached_pmid` | Cached PMID:99999999 + verbatim snippet passes Layer 4 |
| `test_layer4_rejects_non_verbatim_snippet` | Non-verbatim snippet causes Layer 4 to FAIL |
| `test_qc_auto_profile_legacy_for_corpus_sample` | `auto` profile assigns legacy to corpus files |
| `test_qc_auto_profile_ai_curated_for_fixture` | `auto` profile assigns ai_curated when evidence present |
| `test_qc_forced_legacy_skips_layer_4_on_ai_curated_file` | Explicit `--profile legacy` skips Layer 4 |

Layer 4 fixtures are sealed (the cache file ships in `references_cache/PMID_99999999.md`), so the suite has no network dependency.

## Gap report

The full corpus gap analysis lives in [phase2_gap_report.md](phase2_gap_report.md) with these headline numbers:

- Layer 1: **0** failures
- Layer 2: **230** hard failures (190 files), **1,768** legacy-prefix warnings (1,596 files)
- Layer 3: **0** failures
- Layer 4: **0** files with evidence (no-op)

## Reproducibility

```
# Bootstrap (one-time)
python3.10 -m venv .venv-py310
.venv-py310/bin/pip install linkml linkml-runtime jsonschema pyyaml pytest httpx
.venv-py310/bin/pip install linkml-term-validator linkml-reference-validator oaklib

# Run full QC against the corpus
.venv-py310/bin/python scripts/qc.py                    # auto profile
.venv-py310/bin/python scripts/qc.py --profile legacy   # forced
.venv-py310/bin/python scripts/qc.py --json             # machine-readable

# Or via justfile
just qc

# Run pytest
.venv-py310/bin/python -m pytest tests/ -v
```

## Caveats and follow-up

- **Layer 2 has real failures, not just legacy-prefix warnings.** 230 nodes have wrong-prefix data (e.g. a `Protein` node with a MESH ID). These are curation errors that need remediation; surfaced for Phase 2.x.
- **Layer 2 deep mode is not gated by Phase 2.** The lightweight prefix check meets the exit criterion. The richer "does the ID actually resolve" check is available via `--deep` but downloads multi-hundred-MB OAK adapters; defer to CI cache work in Phase 4.
- **`just` is not installed by default.** The `justfile` is the documented entry point per PRD but users will need `brew install just`. All targets also work via direct `python scripts/...` invocations.
- **Two venvs coexist.** `.venv` (Python 3.9) and `.venv-py310` (Python 3.10.4). Phase 3+ work should standardize on `.venv-py310`; the Phase 1 scripts still work in either. Cleanup deferred — not blocking.
- **`requirements.txt` is still the old monolith-era one.** Per the tooling audit, replacing it with a `pyproject.toml`-driven install was scoped for Phase 2. The `pyproject.toml` already lists the right v3 deps; `requirements.txt` deletion / regeneration is a small Phase 2.x follow-up.
- **Phase 1.5's canonicalizer is invoked manually**, not from inside `qc.py`. PRD §5.1.1 anticipates the `/curate` agent calling `canonicalize_predicates.py --write` before validation. Wiring this into the orchestrator (as a pre-step under `ai_curated`) is a Phase 3 task tied to the agent skill.
