---
description: Curate a new DrugMechDB mechanistic path for a (Drug, Disease) pair from PubMed evidence.
argument-hint: <Drug> for <Disease>
allowed-tools: Read, Edit, Write, Bash, Glob, Grep
---

# /curate — Curate a new DrugMechDB mechanistic path

**You are curating a single new mechanistic path connecting `$ARGUMENTS` in DrugMechDB.** The output is one YAML file under `kb/paths/` that (a) passes all four QC layers under the `ai_curated` profile and then (b) clears the **semantic critic** — an independent, grounded reviewer that runs after QC. Only after both pass do you delete the full text and open the PR.

**Before doing anything else, read `AGENTS.md`** at the repo root. It defines the schema contract, ontology table, predicate vocabulary, evidence rules, and tool surface limits. The instructions below are a workflow on top of those rules — when in doubt, the rules in AGENTS.md win.

## Workflow

Follow these steps in order. Don't skip steps.

### 1. Parse the request

Extract `Drug` and `Disease` from `$ARGUMENTS` (e.g. `/curate Aspirin for Myocardial Infarction`). Print both back so the user can correct typos before you spend tokens.

### 2. Resolve identifiers

- Drug → look up DrugBank ID (`DB:DB…`) and MESH ID (`MESH:D…` or `MESH:C…`). At least one must be available; both is better. Search `kb/paths/_index.yaml` first — if the drug is already in DrugMechDB, the IDs are right there.
- Disease → MESH ID (`MESH:D…`).

If you can't find either the drug ID or the disease MESH, stop and ask the user.

### 3. Pick the file index

```
ls kb/paths/ | grep "{drugbank}_{disease_mesh}_"
```

If existing siblings are `_1`, `_2`, your new file is the next free index. Filename: `kb/paths/{drugbank_id}_{disease_mesh}_{N}.yaml`, e.g. `kb/paths/DB00945_MESH_D009203_3.yaml`. The graph `_id` matches the filename stem.

### 4. Find sources via PubMed

You have **no web access** — your only sanctioned source of evidence is `scripts/pubmed_fetch.py` (NCBI / Europe PMC / PubTator3). Finding the right sources is your own job:

1. **Brainstorm the established mechanism** from your own knowledge to form good search queries — but **do not cite PMIDs from memory.** Use your mechanistic understanding to choose search terms, never to invent a citation.
2. **Search PubMed for real papers:**
   ```
   .venv-py310/bin/python scripts/pubmed_fetch.py search "{drug} {disease} mechanism" --max 30
   ```
   Run several searches with different terms (the drug's target, each intermediate step, the pathway) — iterate your queries when a result set is too narrow or off-topic. Favor mechanism-focused papers; avoid pure clinical-outcome trials unless they describe the MOA.
3. **Fetch the abstracts you'll use:**
   ```
   .venv-py310/bin/python scripts/pubmed_fetch.py fetch PMID:xxx PMID:yyy …
   ```
   Abstracts land in `references_cache/PMID_*.md`. **Read each one fully** before drafting — extracting the right verbatim snippet later depends on having the abstract in your context now.

### 5. Escalate to full text only when an abstract is insufficient

For an edge where no cached **abstract** has a verbatim supporting sentence, decide — per edge — whether to read full text. Don't read full text by default; it's slower and usually unnecessary.

1. **Is the paper on-topic for this edge?** If the abstract shows the paper isn't about this step, pick a different PMID instead of reading its body.
2. **Is open-access full text available?** Cheap check, no download:
   ```
   .venv-py310/bin/python scripts/pubmed_fetch.py probe PMID:xxx --json
   ```
   `fulltext_available: true` → escalate. `error:` set → unknown (network), retry. Otherwise stay on the abstract.
3. **Escalate (on-topic AND available):**
   ```
   .venv-py310/bin/python scripts/pubmed_fetch.py fetch PMID:xxx --fulltext
   ```
   This upgrades `references_cache/PMID_xxx.md` to `content_type: full_text` (abstract prepended). Re-read it, then snippet from the body. Cap with `--max-fulltext N` so you don't over-read.

See AGENTS.md §4.4 for the `...`/`[...]` operators and the read-the-context guards (negation, wrong-drug, no bibliography matches).

### 6. Draft the path YAML

- Start the path at the drug node (`label: Drug`, prefix `MESH` or `DB`).
- Walk through 2–6 intermediate biological entities (proteins, pathways, processes, phenotypes) toward the disease node (`label: Disease`, prefix `MESH`).
- Each edge:
  - `key`: pick from the canonical 67 in `src/drugmechdb/schema/biolink_predicates.yaml`.
  - `evidence`: ≥1 `EvidenceItem` with:
    - `reference: PMID:xxxxxxxx`
    - `snippet:` **verbatim** substring of the cached source (abstract, or full text if you escalated) — copy/paste from `references_cache/`, never typed from memory.
    - `supports: SUPPORT` (default) or `PARTIAL` if the abstract is about a closely-related-but-different claim.
    - `evidence_source: HUMAN_CLINICAL | MODEL_ORGANISM | IN_VITRO | COMPUTATIONAL | OTHER` — describes the cited paper's methodology, not yours.
    - `source_tier: FULL_TEXT` **if you took this snippet from escalated full text** (step 5); otherwise omit it (abstract is the default). This is durable provenance: the full-text body is deleted before the PR, so this field is what tells reviewers (via the `full-text-sourced` label) that this snippet isn't CI-verbatim-checkable.

**When an edge has no verbatim-supporting sentence**, in priority order:
1. **Re-source** — try a different sentence, a different PMID, or escalate to full text (step 5) for that edge.
2. **Retain-but-flag (essential edge).** If the edge is needed to keep the path connected drug→disease and you still can't find a verbatim snippet, **keep the edge** with `supports: NO_EVIDENCE` and an `explanation` naming the most-relevant papers that corroborate it. This holds the whole path out of the `ai_curated` profile and flags it for the QC judge / reviewer — it does **not** silently pass.
3. **Drop — only if redundant.** Remove an edge *only* when it is a redundant shortcut or a non-converging branch whose removal leaves the path still connected.

**Never** re-route to a different mechanism just to find something that connects (that invents an unproven path), **never** fabricate or paraphrase a snippet, and **never** ship a disconnected path.

### 7. Canonicalize predicates

```
.venv-py310/bin/python scripts/canonicalize_predicates.py --write {your_file}
```

Idempotent. Lowercases, strips `biolink:` prefixes, replaces underscores with spaces.

### 8. Run QC under ai_curated

```
.venv-py310/bin/python scripts/qc.py --profile ai_curated {your_file}
```

All four layers must pass:

- **Layer 1** (schema) — required fields present, types correct
- **Layer 2** (node ontology) — every CURIE prefix matches its node label
- **Layer 3** (predicate) — every edge key is in the enum
- **Layer 4** (reference) — every snippet is verbatim in the cached source

### 9. Iterate up to 3 times

If any layer fails, look at the report, fix, and re-run. Maximum **3 retries** per AGENTS.md §5.

If you exhaust the budget, write the final state of the file anyway and report **explicitly**, with enough detail for a reviewer to act without re-deriving the problem:

> Unresolved validation failures after 3 retries:
> - Layer N ({layer name}) — {exact validator error message}
> - Offending edge: {source} --{key}--> {target}
> - What you tried: {the snippet(s) / PMID(s) attempted}
> - Suggested fix (if known): {e.g. the validator's fuzzy-match suggestion, or "needs a different source"}

This is an **escalation**: do not keep retrying. Go to **step 11** (which deletes full text) and open a PR flagged for human review with this report in the body — the user / curator (or the PR reviewer) decides whether to merge or fix manually.

### 10. Semantic critic gate (after QC passes)

Once all four QC layers pass, the path is well-formed and every snippet is verbatim — but that is not yet *scientifically* vetted. Run the semantic critic:

```
.venv-py310/bin/python scripts/quality/critic.py {your_file} --round {N}
```

The critic re-derives each edge's support **independently** — grounding in ChEMBL and in papers it retrieves *itself*, i.e. evidence beyond the ones you cited — and judges the chain as a whole. It reads everything in memory and writes nothing to `references_cache/`; its audit (every source it consulted) lands in `provenance/{_id}.semantic_review.yaml`. It reports one verdict:

- **ACCEPT** → proceed to step 11 (clean PR).
- **RE_CURATE** → the critic prints **flagged edges** with *what* is wrong (it will **not** tell you which paper to use or the fix). Treat each flag as a fresh sourcing problem: go back to **step 6**, re-source/redraft the flagged edge(s) from PubMed yourself, re-run QC (step 8), then re-run the critic with `--round {N+1}`. **Cap: 3 rounds** (`--max-rounds 3`). Full text stays in the cache while you are still looping — you need it to re-source.
- **ESCALATE / ABSTAIN** → the round cap was reached, a factual contradiction was found, or the critic couldn't independently ground a judgment. For each unresolved edge, set `supports: NO_EVIDENCE` with an `explanation`, then proceed to **step 11** — which still deletes the full text — and open the PR **flagged for human review** (not auto-mergeable). Escalation does not mean "skip the cleanup": full text is deleted on every terminal outcome.

Never invent a different mechanism to satisfy a flag — re-source the *same* claim, or escalate.

### 11. Finalize — delete full text, then open the PR (every terminal outcome)

This step runs for **all** terminal outcomes: a clean ACCEPT, a QC-exhausted escalation (step 9), or a critic ESCALATE/ABSTAIN (step 10). Full text was only ever needed to verify snippets and ground the critic; both are done, so it must not enter the committed repo:

```
.venv-py310/bin/python scripts/pubmed_fetch.py strip-fulltext --all
```

This reverts every `full_text` cache file to abstract-only, **keeping the abstract and all metadata** (title, authors, journal, year, DOI, PMCID, license) plus the verified snippet in the record and the critic's sidecar — i.e. all the *details* of every paper survive; only the body is dropped.

Then re-validate **exactly as CI will** — full text is gone, so use `--no-verbatim` (a full `qc.py --profile ai_curated` would now fail on any full-text-sourced snippet, since verbatim can't be re-checked without the body; that's expected, and verbatim was already enforced at curation):

```
.venv-py310/bin/python scripts/qc.py --no-verbatim --offline {your_file}
```

Then open the PR via `/create-pr` (clean on ACCEPT; flagged for human review on escalation). CI re-checks Layers 1–3 on the committed corpus and **guards that no `full_text` cache was committed**; it does not re-run verbatim (the source is gone) or the semantic critic (non-deterministic, already run here).

### 12. Report back

Final message to the user must include:

- Path file written: `kb/paths/...`
- Number of nodes, edges, and distinct PMIDs cited
- Final QC result per layer
- QC retry count **and** semantic-critic verdict + round count
- The `provenance/{_id}.semantic_review.yaml` path and how many independent sources the critic consulted
- Any edges left at `supports: NO_EVIDENCE` (flagged for review), and why
- If anything is still failing or escalated: what, and what you tried

## Constraints

- Direct file writes: `kb/paths/` only. `references_cache/` is written by `scripts/pubmed_fetch.py` (never hand-edit it — a pre-edit hook blocks that, which is what makes the verbatim check trustworthy), and `provenance/*.semantic_review.yaml` is written by `scripts/quality/critic.py` (never hand-edit it — it is the critic's audit trail). **Don't** modify the schema, scripts, or other paths.
- You do **not** run the semantic critic's reasoning yourself. It is a separate, independent reviewer (`critic.py`); your job is to act on its flags by re-sourcing — never to argue with it or to read its sidecar to find the fix.
- Bash: only the commands listed in AGENTS.md §6.
- Network: PubMed abstracts + open-access full text via `scripts/pubmed_fetch.py` (it contacts NCBI, Europe PMC, and PubTator3 — see AGENTS.md §6). Your own PubMed search is the source-finding channel — **no WebFetch** and no other external calls.
- If you find yourself wanting to paraphrase an abstract sentence to make a snippet "cleaner," stop — pick a different sentence instead. Layer 4 will reject paraphrases.
