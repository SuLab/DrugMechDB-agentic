# AGENTS.md — Curation rules for DrugMechDB AI agents

This file is the single source of truth for what an AI agent must do when curating or backfilling DrugMechDB mechanistic paths. The `/curate` and `/backfill` slash commands (under `.claude/commands/`) defer to the rules below — any divergence is a bug in those skills.

**Audience:** every Claude Code session invoking `/curate` or `/backfill`. Read this file in full before drafting any path YAML.

**PRD reference:** [PRD v3 §5.1](docs/PRD_v3.md)

---

## 0. The one rule that overrides every other rule

**Every edge in an AI-curated path must carry at least one `EvidenceItem` whose `snippet` is a verbatim substring of the cited source's cached text** — an **abstract** by default, or **full text** when you escalate (see §4.4), from any connected source (§4.1). No paraphrasing. No fabrication.

The matcher (`linkml-reference-validator`) normalizes whitespace, case, and punctuation before comparing and supports a `...` multi-part operator — treat that as a safety net for messy full-text prose, **not** a license to paraphrase (see §4.5).

If you find yourself rewording, summarizing, or "improving" a source sentence — stop. Pick a different sentence.

**When an edge has no verbatim-supporting sentence**, do NOT fabricate and do NOT re-route to a different mechanism just to find something that connects (that invents an unproven path). In priority order:
1. **Re-source** — a different sentence, a different PMID, or escalate to full text (§4.4) for that edge.
2. **Retain-but-flag** — if the edge is needed to keep the path connected drug→disease, keep it with `supports: NO_EVIDENCE` and an `explanation` naming the papers that corroborate it. This holds the whole path out of the `ai_curated` profile and surfaces the edge to the semantic critic (§5 step 8) and the human reviewer; it is never a silent pass.
3. **Drop — only if redundant** — remove an edge only when it is a redundant shortcut or non-converging branch whose removal leaves the path still connected.

Never ship a disconnected path.

**One connected chain — never a shortcut or bypass edge.** An AI-curated path is a *single* causal chain `Drug → molecular target → … → Disease`, where every edge is one mechanistic step and each node (other than the drug) is reached from the step before it. Once you have worked out the mechanism:

1. **Do not add an edge directly from the drug to the disease.** The chain already connects them through its steps; a `Drug —…→ Disease` edge laid on top is redundant — it just restates the conclusion the chain already expresses.
2. **Do not add an edge from the drug (or any node) to a node that is already reached through intermediate steps** — no bypass that skips part of the mechanism (a "short circuit").
3. **End the chain at the disease with a mechanistic/causal predicate** (`causes`, `contributes to`, `manifestation of`, …), never with a clinical-outcome predicate. If your mechanism stops one step short of the disease, add the missing *mechanistic* step — do not bridge the gap with `treats`.
4. **The clinical-outcome predicates — `treats`, `prevents`, `ameliorates`, `exacerbates`, `predisposes`, `affects risk for`, `contraindicated for` — are reserved for the no-mechanism stub only** (next paragraph). They never appear in a path that also works out a mechanism.

**The single-link `Drug —treats→ Disease` path is allowed in exactly one situation:** when, after a genuine search, *no* mechanism can be sourced for the indication. It is a stub that records "someone attempted this," nothing more. It is **never** appended on top of a worked-out mechanism. Decision rule: if you found a mechanism, curate the mechanism and stop; if you truly found none, emit the single stub edge alone. Never both.

These shortcut/bypass edges are hard errors in the deterministic structural checks (`clinical_shortcut`, `short_circuit`, `direct_drug_disease`) and are flagged by the semantic critic. The facts on such an edge are often true — that is not the point; the edge is structurally redundant, so it must not be emitted.

**Source-finding is the curation agent's own job, but it cites only what it fetches.** Form search queries from your own mechanistic knowledge — but never cite a reference or a snippet from memory. **Sourcing is source-agnostic (decided 2026-07):** evidence may come from any connected source/API (PubMed, preprint servers, ChEMBL, clinical trials, reviews, well-sourced references), as long as the source *asserts* the established mechanism. The only acceptable source for an `EvidenceItem.snippet` is text the agent actually fetched and cached (never memory): fetch, read, copy the verbatim sentence; if the cached source has no verbatim supporting sentence, that reference does not enter the path. **Anything beyond an abstract — a full-text body from any source — is fetched only to extract and verify the snippet + its citation metadata, then deleted once the record passes QC**, so the committed repo keeps the snippet and citation but never the copyrighted body.

---

## 1. What you're producing

A single YAML file under `kb/paths/{drug_mesh}_{disease_mesh}_{N}.yaml` (where `N` is the next available index for that drug-disease pair; check `kb/paths/_index.yaml` and existing siblings before picking). Legacy records are keyed by DrugBank ID instead — do not modify them; new records are keyed by the drug's MeSH ID.

The file conforms to the LinkML schema at `src/drugmechdb/schema/drugmechdb.yaml`, top class `MechanisticPath`. Read the schema if anything below conflicts with it — the schema wins.

### Skeleton

```yaml
directed: true
multigraph: true
graph:
  _id: {DrugMESH}_{DiseaseMESH}_{N}              # required, e.g. MESH_D001241_MESH_D009203_1
  drug: aspirin                                   # required
  drug_mesh: MESH:D001241                         # required — new records identify the drug by MeSH
  disease: Myocardial infarction                  # required
  disease_mesh: MESH:D009203                      # required
nodes:                                            # ≥2 nodes
  - id: <ontology:id>
    name: <canonical name>
    label: <BiolinkNodeType>
  - ...
links:                                            # ≥1 edge
  - key: <BiolinkPredicate>                       # must be exact-match in biolink_predicates.yaml
    source: <node id>
    target: <node id>
    evidence:                                     # required for ai_curated; ≥1 item
      - reference: PMID:xxxxxxxx                  # required
        snippet: "Verbatim substring of the abstract."   # required, no quotes in YAML if avoidable
        supports: SUPPORT                         # required: SUPPORT | REFUTE | PARTIAL | NO_EVIDENCE | WRONG_STATEMENT
        evidence_source: HUMAN_CLINICAL           # required: HUMAN_CLINICAL | MODEL_ORGANISM | IN_VITRO | COMPUTATIONAL | OTHER
        explanation: "Optional curator commentary."  # optional
        source_tier: FULL_TEXT                    # optional: set ONLY when the snippet came from escalated full text (else omit = abstract)
references:                                       # optional — secondary URLs (Wikipedia, etc.)
  - https://...
```

---

## 2. Node ontology table

The CURIE prefix of every node `id` **must** match the canonical ontology for that node's `label`. The validator (`scripts/validate_node_ontology.py`) rejects mismatches.

| Biolink `label` | Canonical ID prefix(es) | Legacy (tolerated, do not introduce) |
|---|---|---|
| `Drug` | `MESH`, `DB` | — |
| `Protein` | `UniProt` | — |
| `BiologicalProcess` | `GO` | — |
| `MolecularActivity` | `GO` | — |
| `CellularComponent` | `GO` | — |
| `Cell` | `CL` | — |
| `Pathway` | `REACT` | `reactome` |
| `Disease` | `MESH` | — |
| `PhenotypicFeature` | `HP` | — |
| `GrossAnatomicalStructure` | `UBERON` | — |
| `ChemicalSubstance` | `MESH`, `CHEBI` | — |
| `GeneFamily` | `InterPro` | `Pfam`, `TIGR` |
| `OrganismTaxon` | `NCBITaxon` | `taxonomy` |
| `MacromolecularComplex` | `PR` | — |

**Do not introduce legacy prefixes in new paths.** They exist only because of historical curation; new files must use the canonical prefix.

**Pick the label that fits the actual ontology of the ID, not what feels descriptive.** Concrete pitfalls — these have all appeared in the legacy corpus and are listed here so the agent doesn't repeat them:

- HPO IDs (`HP:xxxxxxx`) are phenotypes, not biological processes. `Tremor (HP:0001337)` → `PhenotypicFeature`, never `BiologicalProcess`.
- Reactome IDs (`R-HSA-…`) are pathways. `Prostaglandin Synthesis (REACT:R-HSA-2162123)` → `Pathway`, never `BiologicalProcess`.
- DrugBank IDs (`DB:`) identify drugs in **legacy** records — label them `Drug` (unless DBMET, see below). New records identify drugs by MeSH, not DrugBank.
- DBMET IDs are DrugBank metabolites appearing in some legacy records — outside the canonical set. If you need to cite one, escalate; do not paper over with the wrong label.

---

## 3. Predicate vocabulary

Every edge `key` must be an **exact** member of the `BiolinkPredicate` enum in `src/drugmechdb/schema/biolink_predicates.yaml`. That enum spans two eras — it still accepts the v1.3.0-era vocabulary the 4,846 legacy records are written in — so membership alone is not enough. **New curation must use only the predicates marked `status: current` in `src/drugmechdb/schema/biolink_predicate_status.yaml`** (47 of 70, pinned to Biolink 4.4.4). QC Layer 3 enforces this for any record carrying evidence.

The high-frequency ones you will reach for:

```
regulates    affects    causes    contributes to    treats    prevents
positively correlated with    negatively correlated with    manifestation of
participates in    occurs in    located in    part of    in taxon
has metabolite    directly physically interacts with    disrupts
```

### 3.0 Polarity lives in qualifiers, not in the predicate name

Biolink's v2→v4 refactor removed `positively regulates`, `decreases activity of`, and the whole
`increases/decreases <aspect> of` family. **Do not use them** — they are `status: legacy_only`.
Say the same thing with a canonical predicate plus qualifiers on the edge:

```yaml
  - key: affects                              # was: decreases activity of
    object_aspect_qualifier: activity         # activity | abundance | expression | synthesis | ...
    object_direction_qualifier: decreased     # increased | decreased | upregulated | downregulated
    source: MESH:D000068877
    target: UniProt:A9UF07

  - key: regulates                            # was: positively regulates
    object_direction_qualifier: increased
    source: UniProt:A9UF07
    target: GO:0008283
```

`affects` requires **both** qualifiers; `regulates` requires `object_direction_qualifier`. Bare, they
assert almost nothing, so Layer 3 rejects them without direction. The permissible values are the
`ObjectAspectEnum` / `ObjectDirectionEnum` enums in `src/drugmechdb/schema/drugmechdb.yaml`, and
`biolink_predicate_status.yaml` gives the exact replacement for every removed predicate.

Read the enum file; the descriptions distinguish near-synonyms (e.g. `regulates` vs `affects`,
`correlated with` vs `causes`).

**You may emit predicates in casual surface forms** — `positively_regulates`, `biolink:positively_regulates`, `Positively Regulates` — and `scripts/canonicalize_predicates.py --write` will normalize them. But the **final** YAML must use the canonical form (lowercase, spaces, no prefix). Always canonicalize before validation.

**You may NOT invent new predicates.** If no canonical predicate fits, escalate per PRD §7 Open Q #3 (adding to the enum requires curator approval + Biolink Model citation). "Valid in Biolink" is not sufficient on its own — the predicate has to be in *our* enum and marked `current`.

### 3.1 Predicate domain/range

Some predicates only make sense between certain node types. Apply each predicate to the node types it is allowed to connect, so the path is typed correctly the first time. These are exactly the `subj_in` / `obj_in` constraints the gate's `type_violation` check reads from `scripts/quality/predicate_polarity.yaml` — the table restates them, it does not add any. "Subject" is the edge `source`, "object" is the edge `target`; **any** means the lexicon does not constrain that end. A constraint is checked only when both endpoint node types are known; predicates not listed here are unconstrained.

| Predicate(s) | Subject (`source`) label | Object (`target`) label |
|---|---|---|
| `treats`, `prevents`, `ameliorates`, `exacerbates`, `contraindicated for` | `Drug`, `ChemicalSubstance` | `Disease`, `PhenotypicFeature` |
| `affects` + aspect `activity` | any | `Protein`, `GeneFamily`, `MacromolecularComplex`, `MolecularActivity`, `Pathway`, `BiologicalProcess` |
| `affects` + aspect `abundance`, `degradation`, `synthesis`, `stability`, `transport`, `uptake` | any | `Protein`, `GeneFamily`, `MacromolecularComplex`, `ChemicalSubstance`, `MolecularActivity` |
| `affects` + aspect `expression` | any | `Protein`, `GeneFamily`, `MacromolecularComplex`, `ChemicalSubstance` |
| `has metabolite` | `Drug`, `ChemicalSubstance` | `ChemicalSubstance`, `Drug` |
| `has phenotype` | any | `PhenotypicFeature` |
| `in taxon` | any | `OrganismTaxon` |
| `occurs in`, `located in`, `expressed in` | any | `CellularComponent`, `GrossAnatomicalStructure`, `Cell`, `OrganismTaxon`, `Pathway` |

Since Biolink 4.4.4 the object constraint follows the **aspect**, not the predicate name, so the lexicon keys those rows `affects|<aspect>` (the legacy `decreases activity of`-style keys are kept for the legacy corpus). An `affects` edge never takes a `Disease` or `PhenotypicFeature` object — reach the disease with a mechanistic/causal predicate (e.g. `causes`, `contributes to`) instead, per §0.

The gate enforces these: an edge whose known endpoint types fall outside the allowed set is flagged as a SOFT `type_violation` and routed to the semantic critic (§5 step 8), so a mis-typed edge is surfaced and returned for correction rather than passing silently. Getting the types right here keeps the edge from bouncing.

*Deferred/tracked:* confirming that the corpus-wide `type_violation` rate drops to ~0 is a re-curation-run check to run later, not part of drafting a single path.

---

## 4. Evidence rules

### 4.1 What counts as evidence

- A `PMID:xxxxxxxx` whose **abstract** appears in PubMed E-utilities (English language, public access).
- When the abstract is insufficient for an edge, the **open-access full text** of the same PMID, fetched via `pubmed_fetch.py fetch --fulltext` (see §4.4). Full text is pulled only from the redistribution-permissive PMC open-access subset.
- The `snippet` is a substring of the cached source under the matcher's normalization (whitespace/case/punctuation-tolerant, with an optional `...` multi-part operator). It does **not** accept paraphrases, summaries, or translations.

### 4.2 What does NOT count

Sourcing is **source-agnostic**: preprints, reviews, and well-sourced references **are** acceptable evidence — provided the `snippet` is a verbatim substring of the fetched source and the source asserts the mechanism (full-text bodies are deleted after QC, §4.4). What still does **not** count:

- **Memory, fabrication, or paraphrase** — a snippet typed from memory, reworded, summarized, or translated.
- **Anything you could not fetch and cache.** If verifiable text can't be retrieved (e.g. a paywalled paper with no published abstract), record `evidence_source: OTHER` with an `explanation` noting the access constraint and hold the edge back (`supports: NO_EVIDENCE`); flag for curator — never cite it as SUPPORT.

### 4.3 Picking the right `supports` and `evidence_source`

| `supports` | When |
|---|---|
| `SUPPORT` | Abstract directly supports the edge claim (the default) |
| `PARTIAL` | Abstract supports a closely related claim but not the exact one (e.g. in a different tissue / species / dose) |
| `REFUTE` | Abstract directly contradicts the claim. Only use after curator confirmation that the database should record the contradiction. |
| `NO_EVIDENCE` | Cited reference does not actually contain evidence for this edge. **Don't add the edge.** This value exists for backfill correction. |
| `WRONG_STATEMENT` | The cited evidence shows the existing claim is factually wrong. Curator territory; do not introduce in `/curate`. |

| `evidence_source` | What kind of paper |
|---|---|
| `HUMAN_CLINICAL` | Patients, cohorts, case reports, RCTs, epidemiology |
| `MODEL_ORGANISM` | Mouse / rat / zebrafish / primate / veterinary in vivo |
| `IN_VITRO` | Cell culture, organoids, biochemical assays |
| `COMPUTATIONAL` | In silico, modelling, ML predictions |
| `OTHER` | Anything not fitting the above (also the slot for paywalled/no-abstract cases) |

If you can't tell, pick `OTHER` and put your reasoning in `explanation`.

### 4.4 Abstract-first; escalate to full text only when needed

Reading full text costs tokens and time, so **default to the abstract** and escalate per *edge*, not per paper:

1. **Try the abstract first.** If a verbatim sentence in the cached abstract supports the edge, use it — done.
2. **If not, triage before escalating** — two cheap checks decide whether full text is worth fetching:
   - *On-topic?* Is the paper actually about this edge (abstract discusses the drug/target/mechanism but doesn't state this specific step)? If it's simply the wrong source, **pick a different PMID** — don't read its body.
   - *Available?* `pubmed_fetch.py probe PMID:x --json` — one metadata call, no download. `fulltext_available: true` (open-access only) → escalate. If `error` is set, that's *unknown* (network) — retry, don't read it as "unavailable."
3. **Escalate only when on-topic AND available:** `pubmed_fetch.py fetch PMID:x --fulltext` upgrades that PMID's cache to `content_type: full_text` (abstract prepended). Re-read it and snippet from the body. `--max-fulltext N` caps escalations per run. **When you snippet from the body, set `source_tier: FULL_TEXT` on that `EvidenceItem`** — it's the durable record that this snippet came from a body that gets stripped pre-PR, and it drives the `full-text-sourced` PR label.
4. **If full text still doesn't support the edge**, record `NO_EVIDENCE` or drop it — never paraphrase.

**Operators (full text, sparingly).** When an unavoidable inline-citation artifact splits the sentence you want, the matcher's `...` quotes the two clean halves: `snippet: "aspirin acetylates ... cyclooxygenase 1"`; `[...]` drops an editorial insert. Prefer a single contiguous sentence when one exists.

**Read the context before accepting a full-text match.** A substring hit can land in a *negated/refuted* sentence (use `REFUTE`/`WRONG_STATEMENT`/`NO_EVIDENCE`, not `SUPPORT`) or in a sentence about a *different drug* in a multi-drug paper (confirm the subject is your entity). Bibliographies and raw table cells are excluded from the cached body, so a match won't come from a reference list.

**Sourcing note (decided 2026-07): source-agnostic.** Evidence may come from any connected source that *asserts* the established mechanism, provided the snippet is verbatim. Full text — any non-abstract body, from any source — is used only to extract and verify the snippet + citation metadata, then **deleted once the record passes QC**, so the repo never redistributes copyrighted text (see §4.4 and the `dmdb-references` skill). *Tooling:* the fetch wrapper (`scripts/pubmed_fetch.py`) currently covers PubMed; wiring the other sources into one fetch-and-ephemeralize layer is tracked separately.

**Full text is ephemeral.** Full-text bodies exist only during curation — to verify snippets and to ground the semantic critic. They are deleted before the PR (§5 step 9, `pubmed_fetch.py strip-fulltext`), so the committed repo carries only abstracts + metadata. Don't rely on a full-text body still being present after a path is merged.

### 4.5 Snippet picking tactics

- Prefer the **shortest** verbatim sentence that supports the edge unambiguously.
- If the abstract uses the inverse phrasing (`X reduces activity of Y`), that supports a `decreases activity of` edge.
- Don't extract from the title alone — the cache stores both, but a sentence from the abstract body is more defensible.
- Avoid sentences that contain hedges (`may`, `suggests`, `appears to`) when a confident sentence is available.

---

## 5. Workflow (the only one)

The `/curate` and `/backfill` skills follow this exact sequence. Deviation is the most common source of validation failure.

1. **Resolve identifiers.**
   - Drug → MESH ID (via PubChem / MeSH). New records identify the drug by MeSH; do not look up or store a DrugBank ID.
   - Disease → MESH ID. MONDO is acceptable for future expansion but not yet wired in v3.

2. **Decide on the next file index.**
   ```
   grep -l "_{drug_mesh}_{disease_mesh}_" kb/paths/ | wc -l
   ```
   New file is `_N+1`.

3. **Find sources via PubMed (your own job).**
   - Brainstorm the established mechanism from your own knowledge to form search queries — but never cite a PMID from memory.
   - `scripts/pubmed_fetch.py search "drug-name disease-name mechanism"` for an initial query; iterate with different terms (the target, each intermediate, the pathway) when a set is too narrow or off-topic.
   - Fetch the candidates you pick: `scripts/pubmed_fetch.py fetch PMID:xxx PMID:yyy …`, and read each abstract fully.
   - The cached text under `references_cache/` (abstract, or full text when you escalate — §4.4) is the sole acceptable source of verbatim snippets.

4. **Draft the path.**
   - Start from the canonical drug node (MESH or DB).
   - Walk through the mechanism to the disease (MESH).
   - Pick predicates from §3 only. When in doubt, pick the more general predicate (`regulates` over `positively regulates` if the directionality isn't clear in the cited sentence).
   - Match each edge to a snippet *while* drafting. When an edge has no verbatim snippet, follow the §0 policy: re-source → retain-but-flag as `NO_EVIDENCE` (essential edges) → drop only if redundant. Never re-route or fabricate.

5. **Canonicalize.**
   ```
   .venv-py310/bin/python scripts/canonicalize_predicates.py --write {your_file}
   ```
   Lowercases, strips `biolink:` prefixes, replaces underscores with spaces.

6. **Validate.**
   ```
   .venv-py310/bin/python scripts/qc.py --profile ai_curated {your_file}
   ```
   Or `just qc -- --profile ai_curated {your_file}` if `just` is installed.

7. **Iterate up to 3 times.** If validation fails, fix and re-run. If you've used all 3 retries:
   - Write the final state anyway and surface a `## Unresolved validation failures` section listing, per failure: the failing layer + exact error, the offending edge (`source --key--> target`), what you tried, and any suggested fix.
   - This is the surfacing rule from PRD §5.1.3 — don't hide failures.
   - This is an **escalation**: stop retrying and go to **step 9** (which deletes full text) to open a PR flagged for human review.

8. **Semantic critic gate (after QC passes).** Deterministic QC proves the path is *well-formed and verbatim*; it does not prove the mechanism is *scientifically* right. Run the critic:
   ```
   .venv-py310/bin/python scripts/quality/critic.py {your_file} --round {N} --max-rounds 3
   ```
   It re-derives each edge's support **independently** — grounding in ChEMBL and in papers it retrieves *itself* (evidence beyond what you cited) — and judges the chain as a whole. It reads everything **in memory**, writes nothing to `references_cache/`, and records its audit (every source consulted) in `provenance/{_id}.semantic_review.yaml`.
   - **ACCEPT** → go to step 9.
   - **RE_CURATE** → the critic prints flagged edges stating *what* is wrong, deliberately **not** the fix or which source to use. Re-source the flagged edge(s) yourself (back to step 4), re-canonicalize, re-run QC (step 6), then re-run the critic with `--round {N+1}`. Cap: **3 rounds**.
   - **ESCALATE / ABSTAIN** → round cap reached, a factual contradiction (`REFUTE`/`WRONG_STATEMENT`) was found, or the critic couldn't independently ground a judgment. Set the unresolved edge(s) to `supports: NO_EVIDENCE` with an `explanation`, then go to **step 9** (which still deletes full text) and open the PR **flagged for human review** — not a clean/auto-mergeable PR.

   The critic is an **independent** reviewer. Do not argue with it, and do not read its sidecar to find the fix — that would defeat the firewall (its broad reading must never leak into the curated evidence). Act on the *flag*, re-source independently.

9. **Finalize — delete full text, then open the PR (every terminal outcome).** This runs on *all* terminal outcomes: a clean ACCEPT, a QC-exhausted escalation (step 7), or a critic ESCALATE/ABSTAIN (step 8). Full text was only needed to verify snippets and ground the critic; both are done. Strip it so it never enters the committed repo — full text persists in the cache **only while you are still looping** (re-curating), never at handoff:
   ```
   .venv-py310/bin/python scripts/pubmed_fetch.py strip-fulltext --all
   ```
   This reverts every `full_text` cache to abstract-only, keeping the abstract, all metadata, the verified snippet, and the critic sidecar — every paper's *details* survive; only the body is dropped. Re-validate with `qc.py --no-verbatim` (verbatim can't re-run without the body; it was enforced at curation). Then open the PR (clean on ACCEPT; flagged for human review on escalation). CI re-runs Layers 1–3 on the committed corpus, **guards that no `full_text` cache was committed**, and does **not** re-run verbatim (source body gone) or the semantic critic (non-deterministic, already run here).

---

## 6. Tool surface (what the skill is allowed to use)

Granted (PRD §5.1.1):

- **File read/write:** write scoped to `kb/paths/`. Read-only for `src/drugmechdb/schema/`, `references_cache/`, `tests/`, `data/`, `docs/`. `references_cache/` (via `pubmed_fetch.py`) and `provenance/*.semantic_review.yaml` (via `critic.py`) are **script-written, not agent-edited** — never hand-edit either. **Don't write anywhere else.** No new top-level directories.
- **Bash:** restricted to:
  - `just qc …` and `python scripts/qc.py …`
  - `python scripts/validate_*.py …`
  - `python scripts/canonicalize_predicates.py …`
  - `python scripts/pubmed_fetch.py …` (incl. `strip-fulltext`)
  - `python scripts/quality/critic.py …` (the post-QC semantic critic)
  - `linkml-validate …` for spot-checks
  - `git status` / `git diff` for awareness; do **not** run `git commit`, `git push`, or destructive git commands.
- **HTTP:** only via the `pubmed_fetch.py` wrapper, the trusted boundary that rate-limits (per host) and writes the cache. The wrapper contacts `eutils.ncbi.nlm.nih.gov` (PubMed abstracts + efetch-pmc), `www.ebi.ac.uk` (Europe PMC full text + availability probe), and `www.ncbi.nlm.nih.gov` (PubTator3 full text). The agent never calls these hosts directly and never `WebFetch`es arbitrary domains — only the wrapper. The wrapper also writes `references_cache/`, which is **script-write-only** (a pre-edit hook blocks the agent from editing it), so the agent cannot author the source text Layer 4 trusts.

Not granted:

- WebSearch / WebFetch to non-PubMed domains, or any direct network call outside the `pubmed_fetch.py` wrapper
- Writing to test fixtures, schema files, or scripts (those are repository design surface; bring up requests with a maintainer)
- Removing or renaming existing paths under `kb/paths/`

---

## 7. Output expectations

When the skill completes successfully:

- **One new file** under `kb/paths/` per `/curate` invocation. (Or modifications to one existing file per `/backfill`.)
- **No untracked changes** to scripts, schema, or other paths.
- **A short status summary** printed back to the user including:
  - The path file written
  - The number of nodes and edges
  - The PMIDs cited
  - The QC layer-by-layer pass/fail result on the final run

If validation didn't pass on first attempt but did within the retry budget, mention that explicitly. If it failed all 3 retries, explain *why* (which layer, which check) so a curator can pick it up.

---

## 8. Anti-patterns observed in legacy corpus — don't repeat

- **Don't label HPO IDs as `BiologicalProcess`** (4 occurrences in legacy data; see Layer 2 gap report).
- **Don't label Reactome IDs as `BiologicalProcess`** (23 occurrences; they're pathways).
- **Don't label MESH disease IDs as `Protein` / `GeneFamily` / `PhenotypicFeature`** unless you've confirmed that's actually what the MESH descriptor refers to. Most cases are mis-bindings that need UniProt / InterPro / HP equivalents instead.
- **Don't write `drug_mesh: null`.** Omit an unknown optional field rather than writing null; the schema is permissive.
- **Don't paraphrase abstracts.** Don't do it.
- **Don't append a shortcut/bypass edge on top of a mechanism** (see §0). The most common form is a redundant `Drug —treats→ Disease` edge added *after* a complete chain, e.g.:
  ```
  # WRONG — 5-edge mechanism PLUS a redundant clinical-outcome shortcut:
  Lisinopril --decreases activity of--> ACE --positively regulates--> Angiotensin II
      --increases activity of--> AT1 receptor --positively regulates--> vasoconstriction
      --causes--> Hypertension
  Lisinopril --treats--> Hypertension          # ← delete this; the chain above already connects drug→disease
  ```
  Keep only the mechanistic chain. `treats` here is a `clinical_shortcut` HARD error. Equally wrong: bridging a mechanism that stops short of the disease with `treats` instead of the missing mechanistic step.

---

*Last updated: June 2026 (Phase 4 — post-QC semantic critic gate + ephemeral full text).*
