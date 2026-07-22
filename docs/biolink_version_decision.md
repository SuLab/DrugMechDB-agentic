# Biolink-version strategy

> **Decision:** the corpus is **re-curated from scratch in the latest Biolink version**
> (forwardfill). There is **no legacy vocabulary to preserve or to translate** — the
> re-curated records are written directly in current Biolink, so storage *is* the current
> vocabulary. Recorded here as the single source of truth; the publish layer references this.

## The choice

The drift audit (`docs/biolink_ontology_drift_report.md`) framed three options: **(A)** pin the old
version, **(B)** migrate stored records, **(C)** keep legacy in storage and translate at publish.
Its leaning was **C** (translate-at-publish), which minimizes churn *when the legacy corpus is kept*.

That premise no longer holds. Because the corpus is **forwardfilled** — every record re-curated from
scratch by the AI curator — the output is authored directly in the **latest Biolink version**. This
is effectively a clean rewrite, not a migration of existing records. So:

- **No version pin to an old Biolink** (rejects A).
- **No record migration** of legacy vocabulary (B is moot — there is no legacy vocabulary in the
  re-curated corpus to migrate).
- **No publish-time translation layer** (C is moot — storage already holds current Biolink; there is
  nothing to translate at export).

## Consequences (issues closed as moot)

- **#19 (publish-time translation to current Biolink)** — moot. Storage is already current Biolink;
  the export layer emits it directly, with no qualifier remap.
- **#54 (predicate→qualifier remap rules)** — moot. The ~20 deterministic remap rules were only
  needed to translate *legacy* predicates at publish; the forwardfilled corpus never uses them.

*Transition caveat:* until forwardfill completes, the stored corpus is still legacy vocabulary. If a
publish of the **legacy** corpus is ever needed **before** forwardfill finishes, #19/#54 can be
reopened for that interim need. The target state (forwardfilled) needs neither.

## Going forward

Keeping the schema aligned with future Biolink releases is handled by the **Biolink-drift monitor**
(`docs/biolink_drift_monitor.md`, `scripts/check_biolink_drift.py`): it detects predicate drift and
opens a human-reviewed draft PR — it never auto-applies a schema change and never auto-assigns a
polarity sign.

### See also
- `docs/biolink_ontology_drift_report.md` — the drift audit that framed the options.
- `docs/biolink_drift_monitor.md` — how future Biolink releases are tracked.
