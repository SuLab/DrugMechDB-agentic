---
name: dmdb-pr-review
description: Review a pull request that adds or edits DrugMechDB path records. Use when reviewing a curation/backfill PR, before approving a merge, or when CI flags a path. Checks QC compliance, path quality, sourcing policy, and diff hygiene.
---

# dmdb-pr-review — reviewing path PRs

Use when reviewing a PR that touches `kb/paths/*.yaml` (or the harness). Pull the
diff with `gh pr diff <n>` / `gh pr view <n>`.

## Review checklist

**1. QC is green.** Every changed record must pass `just qc <file>` for its profile.
CI runs this, but confirm locally for anything that looks borderline. A red Layer is
a blocker, not a nit.

**2. Path quality** (these are correctness criteria — see **dmdb-compliance**):
   - starts **Drug → Protein target**; ends at the Disease node;
   - **3–7 links**; branches only where multiple actions *converge*;
   - **net direction of influence is negative** (drug→disease ⇒ disease decreased);
   - node `label`s use canonical prefixes (**dmdb-terms**); predicates are in-enum.

**3. Evidence & sourcing** (for `ai_curated` records — **dmdb-references**):
   - snippets are verbatim in their cited source (Layer 4 enforces this);
   - sources respect the conservative-sourcing rule: secondary sources that *assert*
     the established mechanism (DrugBank MoA, GO, UniProt, Reactome, reviews). **No
     primary/experimental-literature reconstruction**, **no predicted mechanisms as
     input.** Flag any path that smells like a model-generated hypothesis.

**4. Additive & in-format.** The change must preserve record structure and not
reformat or migrate other records. One (drug, disease) path per PR where practical.

**5. Diff hygiene.** Expected: the `kb/paths/*.yaml` file, new `references_cache/PMID_*.md`,
optional `research/*.md`. **Not** expected: generated indexes/site artifacts, unrelated
files, force-pushed history.

## Verdict

- **Approve** when QC is green, path quality holds, sourcing is conservative, diff is clean.
- **Request changes** with the specific failing layer / criterion and how to fix it
  (point at `just qc-layer N <file>`), so the author can reproduce.
- **Escalate** schema changes or sourcing-policy edge cases to a maintainer
  rather than deciding them in-review.
