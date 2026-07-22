# Node-name normalization convention

> **Decision:** keep **human-friendly** node names. The `name` field is a display label; it is **not
> required to equal the ontology's canonical heading**. Identity is carried by the CURIE `id`, which
> QC Layer 2 validates against the Biolink type. Recorded here as the convention; applies to new
> (forwardfilled) curations.

## Why not force canonical labels

The drift audit found ~7% of node names differ from the ontology's canonical label, and those
differences are **mostly benign** — a drug's common name, or a disease/indication as clinicians name
it, versus a formal ontology heading (e.g. `Tamoxifen` vs a MeSH heading string; `high blood
pressure` vs `Hypertensive disease`). DrugMechDB is meant to be read by people, so a readable name is
a feature, not an error. Nothing is lost by keeping it: the **canonical label is always retrievable
from the CURIE** via OAK, so tools that need the formal heading resolve it on demand.

Forcing every `name` to the canonical heading would also (a) reduce readability for the target
audience and (b) risk a data migration over the existing corpus, which the project forbids
(additive, no reformatting).

## The convention (what a valid `name` must satisfy)

A node's `name` MUST:

1. **Denote the exact entity the CURIE identifies** — it may be a synonym or common name of that
   entity, but never a different, broader, or narrower entity. (A name that names the *wrong* entity
   is a curation error, not a style choice.)
2. Contain **no invisible / zero-width characters and no non-breaking spaces** — enforced
   deterministically by `scripts/validate_node_ontology.py` (issues #24, #66). Ordinary spaces are
   fine.
3. Have **no leading/trailing whitespace** and be **non-empty**.

A node's `name` **need NOT**:

- Match the ontology's canonical label string exactly.
- Use formal ontology capitalization or word order.

## When to normalize *toward* canonical

Only to **fix an error** — when the human name is ambiguous, or actually denotes a different entity
than the CURIE. In that case, correct it to an accurate synonym or the canonical label. This is
correctness, not cosmetic normalization.

## Scope

- **New curations** follow this convention.
- **Existing records** are not rewritten for benign name/label differences (no data migration).

## Possible future enhancement (not required by this convention)

A lightweight Layer-2 check could flag a `name` that matches **no** known synonym of its CURIE (via
OAK synonyms) — a genuine "wrong entity" signal — while explicitly **not** requiring an exact match
to the canonical heading. Tracked as a nice-to-have; the convention above stands without it.
