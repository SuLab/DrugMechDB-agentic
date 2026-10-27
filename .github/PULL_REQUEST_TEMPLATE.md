## What this changes

<!-- One or two sentences. For a record: the drug, the disease, and the mechanism in brief. -->

## Record PRs (`kb/paths/`)

- [ ] One drug–disease path, from a feature branch
- [ ] `python scripts/qc.py --no-verbatim --offline <record>` passes
- [ ] Semantic critic verdict: <!-- ACCEPT / ESCALATE / ABSTAIN -->, sidecar in `provenance/`
- [ ] Full text stripped (`pubmed_fetch.py strip-fulltext --all`)
- [ ] Staged only the record, its cited `references_cache/` files, and its sidecar
- [ ] Any `supports: NO_EVIDENCE` edge is explained in its `explanation` field

## Code PRs

- [ ] Tests pass (`just test`), and new behaviour has a test
- [ ] No paid API call in tests; reports write repo-relative paths
- [ ] No internal or personal content in the diff

See `CONTRIBUTING.md`.
