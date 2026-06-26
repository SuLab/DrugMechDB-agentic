# Phase 1.5 Report — Predicate Canonicalization

**PRD reference:** [PRD v3 §6 Phase 1.5](PRD_v3.md)
**Date:** May 2026
**Status:** Complete — exit criterion met without rewriting any path files

## Exit criterion

> 100% of edge `key` values across `kb/paths/` are members of `BiolinkPredicate`.

**Result:** met. 32,641 edges scanned across 4,846 path files; 0 unmapped predicates.

## Headline finding

The corpus is **already fully canonical**. Every distinct edge `key` in `kb/paths/` is a member of the `BiolinkPredicate` enum declared in [`biolink_predicates.yaml`](../src/drugmechdb/schema/biolink_predicates.yaml).

| | Count |
|---|---|
| Distinct keys in corpus | 67 |
| Members of `BiolinkPredicate` enum | 67 |
| Intersection | **67** |
| Keys in corpus not in enum | **0** |
| Enum members not used in corpus | 0 |

This is consistent with the schema header note ("Frequencies are counts from the 4,846-path corpus as of April 2026") — the enum was derived from this corpus, so every legacy form is already represented.

## What Phase 1.5 still delivered

Even though no path files needed rewriting today, Phase 1.5 is a **prerequisite for Phase 2 Layer 3** and for the AI agent's `/curate` workflow, where agent-emitted predicates can drift in surface form (case, underscores, Biolink CURIE prefix). The artifacts below are required infrastructure regardless of current data:

1. [`data/predicate_aliases.yaml`](../data/predicate_aliases.yaml) — landing zone for hand-curated lexical aliases. Currently empty (no lexical drift in the corpus); Phase 2 will grow it as agent output surfaces new forms.
2. [`scripts/canonicalize_predicates.py`](../scripts/canonicalize_predicates.py) — idempotent rewriter. Dry-run by default (`--write` to apply). Acts as both a one-shot migration tool and the canonicalization step the agent will invoke before validation.
3. [`docs/phase1_5_canonicalization_summary.json`](phase1_5_canonicalization_summary.json) — machine-readable run summary, regenerated on every invocation.

## Normalization pipeline

`scripts/canonicalize_predicates.py` applies the following steps to every edge `key`, in order, *before* consulting the lexical alias map:

1. Strip leading/trailing whitespace.
2. Collapse internal whitespace runs to a single space.
3. Strip a leading `biolink:` CURIE prefix (case-insensitive).
4. Replace underscores with spaces.
5. Lowercase.
6. Look up in `data/predicate_aliases.yaml`; replace if mapped.
7. Verify the result is a member of `BiolinkPredicate`.

These trivial normalizations are intentionally *not* stored in the alias file — they apply universally, so listing them would be noise. Only true *lexical* drift (different words for the same concept) belongs in the alias file.

### Worked examples (verified)

| Input | Pipeline output | In enum? |
|---|---|---|
| `'positively regulates'` | `'positively regulates'` | ✓ |
| `'Positively Regulates'` | `'positively regulates'` | ✓ |
| `'positively_regulates'` | `'positively regulates'` | ✓ |
| `'biolink:positively_regulates'` | `'positively regulates'` | ✓ |
| `'BIOLINK:positively regulates'` | `'positively regulates'` | ✓ |
| `'  positively  regulates  '` | `'positively regulates'` | ✓ |
| `'unknown predicate xyz'` | `'unknown predicate xyz'` | ✗ (flagged) |

## How Phase 2 should use these artifacts

- **Pre-validate every agent draft.** The `/curate` skill should call `canonicalize_predicates.py --write` against its draft path file before running `linkml-validate`. Trivial drift (case, underscore) is silently corrected; true unknown predicates produce a non-zero exit status with a list of unmapped values that the agent can either retry (with stronger constraints) or escalate.

- **Layer 3 validator becomes trivial.** After canonicalization, Layer 3 just confirms every `key` is in the enum. The current [`phase1_validate_all.py`](../scripts/phase1_validate_all.py) already enforces this via the LinkML schema's `BiolinkPredicate` enum constraint.

- **Adding a new canonical predicate** (PRD §7 Open Q #3) is a two-step change: add the entry to `biolink_predicates.yaml` (with a Biolink Model citation in the description) *and*, if any legacy surface form mapped to it, add an alias entry. Domain-curator approval is required per the governance section of the PRD.

## Unmapped predicates: escalation queue

**Empty.** No escalations to curators required as of this Phase 1.5 close.

## Reproducibility

```
.venv/bin/python scripts/canonicalize_predicates.py            # dry-run (default)
.venv/bin/python scripts/canonicalize_predicates.py --write    # apply changes
.venv/bin/python scripts/canonicalize_predicates.py --report-only  # enum/alias info only
```

The latest dry-run output is preserved verbatim in `phase1_5_canonicalization_summary.json`:

```
Edges scanned       : 32641
Files touched       : 0 (dry-run, not written)
Rewrite types       : 0
Unmapped predicates : 0
```

## Caveats and follow-ups

- **The enum may itself drift from upstream Biolink Model.** Several enum members (e.g. `'is metabolite of'`, `'has output'`) are correct for DrugMechDB but may diverge from the canonical Biolink Model spelling. This Phase 1.5 work treats the DrugMechDB enum as authoritative — auditing the enum against Biolink Model upstream is a separate Phase 2 task (PRD §9 risks: "Biolink Model version drift").
- **The corpus had legacy field names but not legacy predicates.** Past curation churn appears to have already normalized predicate names (likely via `scripts/update_occurs_in_preserving_format.py` and similar one-shots). Phase 1 audited those scripts; future migrations should go through the canonicalizer instead of bespoke regex rewrites.
- **Phase 2 will discover new aliases.** Once the agent starts drafting paths, expect Biolink Model surface forms (often with underscores, sometimes with slightly different word choice) to land in the alias file. The empty `aliases: {}` block today is the right starting state, not a permanent one.
