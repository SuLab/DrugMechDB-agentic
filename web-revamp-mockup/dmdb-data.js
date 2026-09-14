/*
 * dmdb-data.js — the single data-access layer for the DrugMechDB site.
 *
 * WHY THIS EXISTS
 * Every page reads data ONLY through `window.DMDB` (below) — never from raw
 * globals or hardcoded markup. Today DMDB serves the bundled sample data
 * (data.js). To go LIVE on the real re-curated corpus you change ONE thing:
 * flip `SOURCE` to "live" and make sure the JSON files named in `ENDPOINTS`
 * exist. No page markup changes — that is the whole point of this layer.
 *
 * The publish step (see scripts/rebuild_monolith.py and
 * scripts/compute_dashboard_metrics.py) should emit exactly these JSON shapes:
 *   - index.json      : Array of browse rows      (same shape as window.DMDB_INDEX)
 *   - records/<id>.json: one full record           (same shape as window.DMDB_RECORD)
 *   - dashboard.json   : the dashboard metrics      (superset of SAMPLE_DASHBOARD)
 *
 * dashboard.json is built by scripts/compute_dashboard_metrics.py from the real
 * corpus + QC gate + structural scorer. It carries every SAMPLE_DASHBOARD panel
 * (each with its `measured` flag) plus extra computed panels (path-length
 * distribution, node-type coverage, structural-quality rollup). Pages read only
 * the keys they need, so the extra panels are additive and safe to ignore.
 *
 * Everything is async so the "sample" and "live" code paths are identical to the
 * caller — pages `await DMDB.getRecord(id)` today and unchanged tomorrow.
 */
(function () {
  "use strict";

  // ── THE SWAP POINT ──────────────────────────────────────────────────────────
  const SOURCE = "live";                 // "sample" (bundled data.js) | "live" (fetch JSON)
  // LIVE: data/ is built from the agentic curation runs by
  // scripts/build_site_data.py (135 records across 4 runs). Re-run it after a curation.
  const ENDPOINTS = {
    index:     "data/index.json",
    record:    (id) => `data/records/${encodeURIComponent(id)}.json`,
    dashboard: "data/dashboard.json",
  };
  // ─────────────────────────────────────────────────────────────────────────────

  async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`DMDB: fetch failed (${res.status}) for ${url}`);
    return res.json();
  }

  /*
   * Sample dashboard metrics (mockup placeholders). Panels mirror the current
   * dashboard page plus Dismech's compliance/priority views. Each metric carries
   * `measured`: whether the pipeline actually computes & stores it today.
   *   true    -> derivable now (qc.py / structural_quality.py / corpus counts)
   *   partial -> partially available
   *   false   -> NOT yet measured/stored — needs a pipeline metric (tracked as a GH issue)
   * The `measured` flags are the source of truth for "what do we still need to wire".
   */
  const SAMPLE_DASHBOARD = {
    totals: { paths: 4846, drugs: 2388, diseases: 1901, avg_path_length: 4.6, measured: true },

    // QC gate outcome across the corpus (scripts/qc.py) — measurable now.
    qc_compliance_by_layer: {
      measured: true,
      layers: [
        { layer: 1, name: "schema",         pass: 4846, fail: 0 },
        { layer: 2, name: "node ontology",  pass: 4616, fail: 230 },
        { layer: 3, name: "predicate enum", pass: 4846, fail: 0 },
        { layer: 4, name: "evidence",       pass: 0,    fail: 0, note: "ai_curated only; 0 legacy paths carry evidence yet" },
      ],
    },

    // Curation provenance (model / prompt version / date) — needs issue #55.
    provenance: {
      measured: false,
      note: "Per-record provenance (model, prompt version, run id, date) is not captured yet — issue #55.",
      by_model: [], by_month: [],
    },

    // Indication coverage: approved indications that have vs lack a mechanism path.
    indication_coverage: {
      measured: false,
      note: "Coverage vs an external approved-indication list is not computed yet — needs a coverage metric.",
      covered: null, total: null,
    },

    // Predicate usage across the corpus — measurable now (count link keys).
    predicate_distribution: {
      measured: true,
      top: [
        { predicate: "decreases activity of", count: 0 },
        { predicate: "causes", count: 0 },
        { predicate: "positively regulates", count: 0 },
      ],
      note: "Sample; the live builder fills counts from the corpus.",
    },

    // Records the structural scorer flags — partially available (structural_quality.py
    // reports HARD/SOFT flags; it is a scorer, not yet a stored per-record status).
    records_needing_attention: {
      measured: "partial",
      note: "structural_quality.py flags these on demand; not persisted per record yet.",
      items: [],
    },

    // Priority-to-curate list (Dismech-style) — needs the work-queue metric (issue #13).
    priority_to_curate: {
      measured: false,
      note: "Prioritized worklist of what to (re)curate next — needs the work queue, issue #13.",
      items: [],
    },
  };

  // ── public API — the ONLY surface pages should use ──────────────────────────
  window.DMDB = {
    source: SOURCE,
    async getIndex() {
      return SOURCE === "live" ? fetchJSON(ENDPOINTS.index) : (window.DMDB_INDEX || []);
    },
    async getRecord(id) {
      if (SOURCE === "live") {
        if (!id) {                                     // no ?id= -> first index row
          const idx = await fetchJSON(ENDPOINTS.index);
          if (!idx.length) throw new Error("DMDB: index.json is empty");
          id = idx[0].id;
        }
        return fetchJSON(ENDPOINTS.record(id));
      }
      const r = window.DMDB_RECORD || null;                 // sample ships a single record
      return (r && id && r.graph && r.graph._id !== id) ? r : r;
    },
    async getDashboard() {
      // live -> the metrics file emitted by scripts/compute_dashboard_metrics.py
      // (ENDPOINTS.dashboard = "data/dashboard.json"); sample -> bundled placeholders.
      return SOURCE === "live" ? fetchJSON(ENDPOINTS.dashboard) : SAMPLE_DASHBOARD;
    },
  };
})();
