---
description: Open a pull request for curated/backfilled DrugMechDB path work, after validating it.
argument-hint: [branch-name or short description]
allowed-tools: Read, Bash, Glob, Grep
---

# /create-pr — open a PR for path work

Package the current path work into a clean, QC-green pull request. Mirrors Dismech's
`/create-pr`, adapted to this repository's QC gate.

**This command runs for EVERY terminal outcome — a clean accepted path, *or* an
escalation** (QC exhausted its 3 retries, or the semantic critic returned
ESCALATE/ABSTAIN). Full text is deleted here regardless; an escalation simply opens a
PR flagged for human review instead of a clean one.

## Steps

1. **Confirm curation finished.** The record should already have passed deterministic
   QC (Layers 1–4, *with* verbatim, against the full-text-bearing cache) and been run
   through the semantic critic during `/curate`. Note the critic verdict and whether any
   edge is `supports: NO_EVIDENCE` — that decides clean-PR vs human-review-PR below.

2. **Delete full text — non-negotiable, every PR.** Full text was only needed to verify
   snippets and ground the critic; both are done. Strip it so no body ever enters the repo:
   ```bash
   python scripts/pubmed_fetch.py strip-fulltext --all
   ```
   This reverts every `full_text` cache to abstract-only, **keeping the abstract and all
   metadata** (title, authors, journal, year, DOI, PMCID, license) — the recorded "details"
   of every paper. The full-text snippet you already verified stays in the record; its body
   does not. (A CI guard rejects any PR that still carries a `full_text` cache file.)

3. **Re-validate exactly as CI will** — full text is now gone, so use `--no-verbatim`
   (Layers 1–3); verbatim was enforced once at curation and cannot be re-run without the body:
   ```bash
   git status --short kb/paths/ references_cache/
   python scripts/qc.py --no-verbatim --offline kb/paths/<changed-file>.yaml
   ```
   If a layer is red, **stop and fix it** (use **dmdb-compliance** to diagnose).

4. **Scope the diff.** One (drug, disease) path per PR where practical. Stage only what
   belongs (targeted `git add`, never `git add -A`):
   - the `kb/paths/*.yaml` record(s);
   - the `references_cache/PMID_*.md` the evidence cites (now abstract-only — confirm none
     are `content_type: full_text`);
   - the `provenance/<_id>.semantic_review.yaml` critic audit sidecar;
   - optional `research/*.md` dossier(s).
   **Exclude** generated indexes/site artifacts and unrelated files.

5. **Branch.** If on the default branch, create a feature branch first —
   never commit path work directly onto the shared branch:
   ```bash
   git checkout -b curate/<drug>-<disease>
   git add kb/paths/<file>.yaml references_cache/PMID_*.md provenance/<_id>.semantic_review.yaml
   git commit -m "Curate <Drug> for <Disease> path"
   git push -u origin curate/<drug>-<disease>
   ```

6. **Open the PR** with `gh pr create`. Base branch = the team's integration branch
   (**confirm the base branch with the maintainers**; don't assume). Body should state:
   - the (drug, disease) pair and `_id`;
   - node/edge count and the path shape (drug→target→…→disease);
   - profile (legacy / ai_curated) and QC result (Layers 1–3 green; verbatim done at curation);
   - the semantic-critic verdict + how many independent sources it consulted;
   - PMIDs cited (for ai_curated) and the sourcing basis.

   **If the critic verdict was ESCALATE/ABSTAIN, or any edge is `NO_EVIDENCE`:** mark the
   PR for human review (open as a draft or add a `needs-human-review` label) and say so in
   the body — it is **not** auto-mergeable. The point of this PR is to get the unresolved
   issue in front of a human, with the full text already stripped.

7. **Report** the PR URL and a one-line summary back to the user.

## Guardrails

- **Strip full text before every PR (step 2), no exceptions** — clean or escalated. A CI
  guard fails the PR if any committed `references_cache/*.md` is still `content_type:
  full_text`, so a missed strip is caught, but don't rely on it: run step 2 yourself.
- The pre-edit hook already gates each write, but **re-run `qc.py --no-verbatim` after the
  strip** — that is exactly the gate CI enforces on the committed corpus.
- Flag any **schema change** or **sourcing-policy edge case** for maintainer review
  in the PR body; don't bury it.
- Never force-push a shared or someone else's branch.
