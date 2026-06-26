---
description: Open a pull request for curated/backfilled DrugMechDB path work, after validating it.
argument-hint: [branch-name or short description]
allowed-tools: Read, Bash, Glob, Grep
---

# /create-pr — open a PR for path work

Package the current path work into a clean, QC-green pull request. Mirrors Dismech's
`/create-pr`, adapted to this repository's QC gate.

## Steps

1. **Validate first — non-negotiable.** Run `just qc` on every changed record:
   ```bash
   git status --short kb/paths/
   just qc kb/paths/<changed-file>.yaml   # repeat per file, or `just qc` for all
   ```
   If any layer is red, **stop and fix it** (use **dmdb-compliance** to diagnose).
   Do not open a PR on red QC.

2. **Scope the diff.** One (drug, disease) path per PR where practical. Stage only
   what belongs (targeted `git add`, never `git add -A`):
   - the `kb/paths/*.yaml` record(s);
   - new `references_cache/PMID_*.md` the evidence cites;
   - optional `research/*.md` dossier(s).
   **Exclude** generated indexes/site artifacts and unrelated files.

3. **Branch.** If on the default branch, create a feature branch first —
   never commit path work directly onto the shared branch:
   ```bash
   git checkout -b curate/<drug>-<disease>
   git add kb/paths/<file>.yaml references_cache/PMID_*.md
   git commit -m "Curate <Drug> for <Disease> path"
   git push -u origin curate/<drug>-<disease>
   ```

4. **Open the PR** with `gh pr create`. Base branch = the team's integration branch
   (**confirm the base branch with the maintainers**; don't assume). Body should state:
   - the (drug, disease) pair and `_id`;
   - node/edge count and the path shape (drug→target→…→disease);
   - profile (legacy / ai_curated) and QC result (all layers green);
   - PMIDs cited (for ai_curated) and the sourcing basis.

5. **Report** the PR URL and a one-line summary back to the user.

## Guardrails

- The pre-edit hook already gates each write, but **re-run `just qc` before the PR** —
  it's the gate CI will enforce.
- Flag any **schema change** or **sourcing-policy edge case** for maintainer review
  by the maintainers in the PR body; don't bury it.
- Never force-push a shared or someone else's branch.
