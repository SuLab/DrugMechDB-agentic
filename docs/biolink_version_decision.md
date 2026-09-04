# Biolink-version strategy

> **Decision:** DrugMechDB targets a **pinned current Biolink release** — **4.4.4** — and
> AI-curated records are written in it, qualifiers and all. The legacy corpus stays in its
> own vocabulary until forwardfill replaces it. Recorded here as the single source of truth;
> the publish layer references this.

## The choice

The drift audit (`docs/biolink_ontology_drift_report.md`) framed three options: **(A)** pin the old
version, **(B)** migrate stored records, **(C)** keep legacy in storage and translate at publish.

An earlier revision of this document recorded the strategy as *"re-curated from scratch in the latest
Biolink version, so storage **is** the current vocabulary"* and closed #19 and #54 as moot on that
basis. **That premise did not hold.** The curator was handed the legacy 67-predicate enum
(`AGENTS.md` §3, `.claude/commands/curate.md`) and QC Layer 3 enforced it, so forwardfilled records
came out in the *legacy* vocabulary: measured against Biolink 4.4.4, **323 of 558 edges (58%)** in
the 135 AI-curated records used predicates Biolink had already removed. Writing "latest Biolink" in
a policy document does not make the gate produce it.

The corrected strategy is **B, scoped to the AI-curated corpus**:

- **Pin the Biolink release** (4.4.4) in `src/drugmechdb/schema/biolink_predicate_status.yaml`,
  rather than tracking a moving `master`.
- **The enum spans both eras.** `biolink_predicates.yaml` still accepts the v1.3.0-era vocabulary,
  because the 4,846 legacy records in `kb/paths/` are written in it and are not being rewritten.
- **The gate decides per profile.** Layer 3 permits any enum member for `legacy` records and only
  `status: current` members for `ai_curated` ones. This is what actually holds new curation to
  current Biolink — the contract text alone did not.
- **Records already curated were migrated**, not re-curated, by `scripts/migrate_predicates.py`
  (a deterministic transform driven by the same status file the gate reads).

## Consequences

- **#19 (publish-time translation to current Biolink)** — still moot *for AI-curated records*
  (they are stored in current Biolink, so the exporter emits it directly), but **live again for the
  legacy corpus**: publishing `kb/paths/` as current Biolink needs the translation, because those
  records keep the legacy vocabulary until forwardfill reaches them.
- **#54 (predicate→qualifier remap rules)** — **not moot.** The rules are implemented as
  `scripts/migrate_predicates.py` + the `replacement:` blocks in
  `src/drugmechdb/schema/biolink_predicate_status.yaml`. They were used to migrate the AI-curated
  corpus and are what a legacy publish would reuse.

## What has no mechanical answer

Three removed predicates have no faithful qualifier form and are never rewritten automatically —
they carry `needs_human_decision: true` in the status file:

| Predicate | Why |
|---|---|
| `affects risk for` | Direction is unspecified; 4.4.4 splits it into `associated with increased likelihood of` / `associated with decreased likelihood of`. Needs a per-edge reading of the evidence. |
| `increases response to` / `decreases response to` | Biolink 4.4.4 has no `response` aspect in `GeneOrGeneProductOrChemicalEntityAspectEnum`. |

These appear only in the legacy corpus (1–82 edges each), never in the AI-curated records.

## Going forward

Keeping the pin current is handled by the **Biolink-drift monitor**
(`docs/biolink_drift_monitor.md`, `scripts/check_biolink_drift.py`): it compares the committed enum
against a Biolink ref and reports the delta for a human-reviewed draft PR — it never auto-applies a
schema change and never auto-assigns a polarity sign. When a release moves the pin, update
`biolink_predicate_status.yaml` and re-run `scripts/migrate_predicates.py --check`.

### See also
- `docs/biolink_ontology_drift_report.md` — the drift audit that framed the options.
- `docs/biolink_drift_monitor.md` — how future Biolink releases are tracked.
- `src/drugmechdb/schema/biolink_predicate_status.yaml` — the pin, the per-predicate status, and the
  replacement each removed predicate maps to.
