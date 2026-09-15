# Biolink Drift Monitor

> **Status:** operational tooling. Detects when the upstream Biolink Model's
> **predicate vocabulary** drifts from the predicate set this project accepts, and
> prepares that drift for a **human** to review. Nothing it produces is ever applied
> automatically. Related background: `docs/biolink_version_decision.md` (the locked
> "translate at the publish layer, don't migrate stored records" policy) and
> `docs/biolink_ontology_drift_report.md` (the one-off audit this monitor operationalizes).

---

## 1. Why this exists

The corpus stores edges keyed by a fixed vocabulary of Biolink predicates
(`src/drugmechdb/schema/biolink_predicates.yaml`; `biolink_predicate_status.yaml` records
which of them the pinned Biolink release still defines), each also assigned a
direction-of-influence sign in `scripts/quality/predicate_polarity.yaml`. Biolink evolves
independently — the v2→v4 **qualifier refactor** already folded many of our high-frequency
predicates (`positively regulates`, `increases activity of`, …) into `regulates`/`affects`
plus qualifiers. When that happens our stored vocabulary silently ages out of the current
model.

The monitor answers, on demand: **"How far has Biolink drifted from us, and which predicates
would need a human decision (including a polarity sign) if we reacted to it?"** It does **not**
react on its own — the locked policy is to keep the legacy vocabulary in storage and translate
to current Biolink only at the publish/export layer, so any change to the enum is a deliberate,
human-reviewed act.

## 2. What it is

- **`scripts/check_biolink_drift.py`** — the monitor. Read-only w.r.t. committed files.
- **`.github/workflows/biolink-drift.yml`** — a **dormant** workflow (manual dispatch only;
  a monthly `schedule:` is present but commented out) that runs the script, publishes a report
  artifact, and — only when a maintainer explicitly opts in — opens a **draft** PR.

## 3. What the script does

1. Reads **our** predicate set from the LinkML schema enum and the polarity lexicon.
2. Fetches the **latest** Biolink Model YAML from GitHub raw (cached under `.cache/`, which is
   gitignored). Predicates are the model's `slots` whose `is_a`/`mixins` ancestry reaches the
   root predicate slot `related to`.
3. Computes drift:
   - **removed** — our predicate is no longer a Biolink predicate;
   - **deprecated** — present upstream but flagged `deprecated`;
   - **renamed** — our CURIE now resolves to a different canonical name;
   - **added** — Biolink predicates we don't use (informational);
   - **polarity coverage** — schema predicates with no polarity entry, and stale polarity
     entries with no schema predicate.
4. Prints a human-readable report (or `--json`).
5. Emits the list of predicates that would need a **human polarity-sign decision** (removed /
   deprecated / uncovered). **It never assigns a sign.**

### Cardinal rules (enforced in code)

- **Read-only on committed files.** Reports go to stdout or an explicit `--report-dir` (a scratch
  path). `--emit-enum` refuses to write over the committed schema or polarity file.
- **Human-reviewed draft PR only.** `--emit-enum` produces a *drift-annotated copy* of the enum:
  every value is preserved and drift is flagged inline with `# !! BIOLINK-DRIFT` markers. It never
  deletes a predicate (that would break existing records) and never edits polarity.
- **No automatic polarity signs.** Ever.

## 4. Running it locally

```bash
# Report to stdout (fetches + caches the latest Biolink model on first run):
python scripts/check_biolink_drift.py

# Also list the Biolink predicates we don't use, and write md + json to a scratch dir:
python scripts/check_biolink_drift.py --show-added --report-dir /tmp/drift

# Reproducible / no-network run (uses the cache; errors if absent):
python scripts/check_biolink_drift.py --offline

# Pin a specific Biolink release instead of latest:
python scripts/check_biolink_drift.py --biolink-ref v4.2.2

# Produce the drift-annotated enum a draft PR would carry (scratch path only):
python scripts/check_biolink_drift.py --emit-enum /tmp/drift/proposed_predicates.yaml

# Use in a gate (exit 1 if any removed/renamed/deprecated predicate is found):
python scripts/check_biolink_drift.py --fail-on-drift
```

Exit status: `0` normally; `1` with `--fail-on-drift` when drift is found; `2` on a fetch/parse
error or if `--emit-enum` is pointed at a committed source file.

## 5. Running it in CI

The workflow is dormant — trigger it from the **Actions** tab → *Biolink drift monitor* →
*Run workflow*. Inputs:

- **`biolink_ref`** — Biolink git ref to check against (default `master` = latest).
- **`open_draft_pr`** — default `false`. Leave it `false` to only get the report. Set it `true`
  **only** when you intend to open a review PR.

Jobs:

- **`drift-report`** (read-only, always) — runs the monitor, prints the report into the run
  **summary**, and uploads it as the **`biolink-drift-report`** artifact (`.md` + `.json`).
- **`propose-draft-pr`** (guarded) — runs only when `open_draft_pr == true`. It copies the
  drift-annotated enum over the schema on a throwaway branch and opens a **draft** PR. This job
  is the *only* thing with write scope, it never runs on a schedule or by default, and the PR it
  opens is a draft that is **never auto-merged**.

To let the monitor run on a cadence, uncomment the `schedule:` block in the workflow and confirm
the repo's Actions token has the needed scope. Even scheduled, it only ever produces the report
artifact — the draft-PR job stays gated on the explicit `open_draft_pr` input.

## 6. Reviewing a drift PR (the human step)

1. Open the run's **`biolink-drift-report`** artifact and read `biolink_drift_report.md`.
2. For each `removed` predicate, decide per the locked policy — usually **keep it in storage** and
   ensure the publish/export layer maps it to the current Biolink term + qualifiers. Do **not**
   simply delete it from the enum.
3. For any predicate that genuinely enters or leaves our accepted set, assign or revisit its
   **polarity sign** in `scripts/quality/predicate_polarity.yaml` by hand — the monitor only tells
   you *which* predicates need a decision, never *what* the sign is.
4. If a draft PR was opened, resolve each `# !! BIOLINK-DRIFT` marker, remove the DRAFT banner,
   and only then take it out of draft for normal review + merge.
