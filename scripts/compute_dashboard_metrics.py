"""
Compute the curation-dashboard metrics from the committed corpus + QC gate.

WHAT THIS IS
    A read-only publish step: it reads every kb/paths/*.yaml record, runs the
    real QC layer validators (scripts/validate_*.py) and the structural scorer
    (scripts/quality/structural_quality.py), aggregates the results, and writes
    web-revamp-mockup/data/dashboard.json — the shape the site data adapter
    (web-revamp-mockup/dmdb-data.js, getDashboard() live-mode) consumes.

    It NEVER writes to kb/ or any curation file. It only reads records.

WHY IT EXISTS
    The dashboard page (web-revamp-mockup/dashboard.html) shows several panels
    that were hardcoded placeholders because nothing computed them. This script
    computes every metric that IS derivable from the corpus today, and for the
    metrics that are NOT yet derivable (they need external data or per-record
    metadata that isn't captured) it stores an explicit `measured: false` marker
    with a note rather than fabricating a number.

THE `measured` CONTRACT (mirrors dmdb-data.js SAMPLE_DASHBOARD)
    true    -> computed from the corpus / QC gate / structural scorer, stored here.
    false   -> NOT computable yet (needs external data or uncaptured metadata);
               value fields are null/empty and `note` says why.
    "partial" is not used by this builder; a panel is either fully computed or
    explicitly not-yet-computable, with any partially-available side metric
    surfaced as its own computed field.

OUTPUT SCHEMA (web-revamp-mockup/data/dashboard.json)
    generated_at            ISO-8601 UTC build timestamp
    generator               this script's repo-relative path
    corpus                  {n_records, paths_dir}
    totals                  {measured, paths, drugs, diseases, avg_path_length, ...}
    qc_compliance_by_layer  {measured, profile_counts, layers:[{layer,name,pass,fail,note?}]}
    provenance              {measured, by_profile, by_model, by_month, ...}
    indication_coverage     {measured:false, covered, total, pct, + computable side metrics}
    predicate_distribution  {measured, total_edges, distinct_predicates, top:[{predicate,count}]}
    path_length_distribution{measured, min, max, mean, median, bins, in_range_3_7}
    node_type_coverage      {measured, types:[{label, node_count, record_count}]}
    structural_quality      {measured, summary, by_code, polarity}
    records_needing_attention {measured, total_flagged, items:[{id,file,issue,layer,severity,code}]}
    priority_to_curate      {measured:false, items, note}

USAGE
    .venv-py310/bin/python scripts/compute_dashboard_metrics.py            # build
    .venv-py310/bin/python scripts/compute_dashboard_metrics.py --stdout   # print, don't write
    .venv-py310/bin/python scripts/compute_dashboard_metrics.py -o path.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"
SCRIPTS = REPO / "scripts"
DEFAULT_OUT = REPO / "web-revamp-mockup" / "data" / "dashboard.json"

# Cap on how many flagged records to embed in records_needing_attention (the
# full count is always reported via total_flagged; the list is a worklist head).
ATTENTION_LIMIT = 200


# ── load the real validators / scorer as modules (scripts/ is not a package) ──
def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

v_schema = _load("dmdb_validate_schema", "scripts/validate_schema.py")
v_nodes = _load("dmdb_validate_node_ontology", "scripts/validate_node_ontology.py")
v_preds = _load("dmdb_validate_predicates", "scripts/validate_predicates.py")
structural = _load("dmdb_structural_quality", "scripts/quality/structural_quality.py")


def iter_files() -> list[Path]:
    return sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


# ── severity ordering for the worklist head ───────────────────────────────────
_SEV_RANK = {"HARD": 0, "SOFT": 1, "INFO": 2}


def build() -> dict:
    files = iter_files()
    n = len(files)

    # QC enums / lexicon loaded once
    pred_enum = v_preds.load_enum()
    lexicon = structural.load_lexicon()

    # accumulators
    drug_mesh, disease_mesh = set(), set()
    drug_names, disease_names = set(), set()
    indications = set()
    link_counts, node_counts = [], []
    predicate_counter: Counter = Counter()
    total_edges = 0
    node_label_counter: Counter = Counter()          # total node occurrences per label
    node_label_records: dict[str, set] = defaultdict(set)  # records containing >=1 of label

    # QC layer pass/fail (per record)
    layer_fail = {1: 0, 2: 0, 3: 0}
    layer2_warn_records = 0
    n_with_evidence = 0

    # structural
    struct_clean = struct_hard_clean = 0
    struct_hard = struct_soft = struct_info = 0
    struct_by_code: Counter = Counter()      # (severity, code) -> count of records with >=1
    polarity_counter: Counter = Counter()

    attention: list[dict] = []

    for i, f in enumerate(files):
        doc = yaml.safe_load(f.read_text())
        if not isinstance(doc, dict):
            doc = {}
        graph = doc.get("graph", {}) or {}
        nodes = doc.get("nodes", []) or []
        links = doc.get("links", []) or []
        rid = graph.get("_id") or f.stem
        frel = rel(f)

        # totals
        drug_mesh.add(graph.get("drug_mesh"))
        disease_mesh.add(graph.get("disease_mesh"))
        if graph.get("drug"):
            drug_names.add(str(graph["drug"]).strip().lower())
        if graph.get("disease"):
            disease_names.add(str(graph["disease"]).strip().lower())
        indications.add((graph.get("drug_mesh"), graph.get("disease_mesh")))
        link_counts.append(len(links))
        node_counts.append(len(nodes))

        # predicates
        for e in links:
            if isinstance(e, dict) and e.get("key") is not None:
                predicate_counter[e["key"]] += 1
                total_edges += 1

        # node-type coverage
        labels_here = set()
        for nd in nodes:
            if isinstance(nd, dict) and nd.get("label") is not None:
                node_label_counter[nd["label"]] += 1
                labels_here.add(nd["label"])
        for lab in labels_here:
            node_label_records[lab].add(rid)

        # evidence detection (profile)
        has_ev = any(isinstance(e, dict) and e.get("evidence") for e in links)
        if has_ev:
            n_with_evidence += 1

        # ── QC layers (reuse the real validators) ──
        l1 = v_schema.validate_file(f)
        l2_fail, l2_warn = v_nodes.validate_file(f)
        l3 = v_preds.validate_file(f, pred_enum)
        if l1:
            layer_fail[1] += 1
        if l2_fail:
            layer_fail[2] += 1
        if l2_warn:
            layer2_warn_records += 1
        if l3:
            layer_fail[3] += 1

        # ── structural scorer ──
        s = structural.analyze(f, lexicon)
        sev = s["severity_counts"]
        if s["clean"]:
            struct_clean += 1
        if s["clean_hard"]:
            struct_hard_clean += 1
        if sev["HARD"] > 0:
            struct_hard += 1
        if sev["SOFT"] > 0:
            struct_soft += 1
        if sev["INFO"] > 0:
            struct_info += 1
        if s.get("polarity"):
            polarity_counter[s["polarity"]] += 1
        seen_codes = set()
        for fl in s["flags"]:
            key = (fl["severity"], fl["code"])
            if key not in seen_codes:
                struct_by_code[key] += 1
                seen_codes.add(key)

        # ── records-needing-attention items (QC failures first, then structural) ──
        for fail in l1:
            attention.append({"id": rid, "file": frel, "layer": 1, "severity": "HARD",
                              "code": "schema", "issue": fail.get("message", "schema violation")})
        for fail in l2_fail:
            attention.append({"id": rid, "file": frel, "layer": 2, "severity": "HARD",
                              "code": "node_ontology", "issue": fail.get("reason", "node ontology violation")})
        for fail in l3:
            attention.append({"id": rid, "file": frel, "layer": 3, "severity": "HARD",
                              "code": "predicate_enum", "issue": fail.get("reason", "predicate not in enum")})
        for fl in s["flags"]:
            if fl["severity"] == "INFO":
                continue
            attention.append({"id": rid, "file": frel, "layer": "structural",
                              "severity": fl["severity"], "code": fl["code"], "issue": fl["msg"]})

        if (i + 1) % 500 == 0:
            print(f"  … {i + 1}/{n} records", file=sys.stderr)

    # ── assemble ──
    link_counts = link_counts or [0]
    length_bins = Counter(link_counts)
    in_range = sum(1 for x in link_counts if 3 <= x <= 7)

    # order attention: HARD before SOFT, QC layers before structural
    attention.sort(key=lambda it: (_SEV_RANK.get(it["severity"], 9),
                                    0 if isinstance(it["layer"], int) else 1,
                                    str(it["id"])))

    # profile counts: a record is ai_curated iff it carries per-edge evidence
    legacy = n - n_with_evidence
    ai_curated = n_with_evidence

    dashboard = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/compute_dashboard_metrics.py",
        "corpus": {"n_records": n, "paths_dir": "kb/paths"},

        "totals": {
            "measured": True,
            "paths": n,
            "drugs": len(drug_mesh - {None}),
            "diseases": len(disease_mesh - {None}),
            "avg_path_length": round(sum(link_counts) / n, 2) if n else 0,
            "avg_nodes": round(sum(node_counts) / n, 2) if n else 0,
            "distinct_drug_names": len(drug_names),
            "distinct_disease_names": len(disease_names),
            "note": "drugs/diseases are distinct MeSH identifiers; avg_path_length is mean edges (links) per path.",
        },

        "qc_compliance_by_layer": {
            "measured": True,
            "profile_counts": {"legacy": legacy, "ai_curated": ai_curated},
            "layers": [
                {"layer": 1, "name": "schema",
                 "pass": n - layer_fail[1], "fail": layer_fail[1]},
                {"layer": 2, "name": "node ontology",
                 "pass": n - layer_fail[2], "fail": layer_fail[2],
                 "note": f"{layer2_warn_records} record(s) carry legacy-prefix warnings (not failures)."},
                {"layer": 3, "name": "predicate enum",
                 "pass": n - layer_fail[3], "fail": layer_fail[3]},
                {"layer": 4, "name": "evidence",
                 "pass": 0, "fail": 0,
                 "note": ("ai_curated only; runs on records with per-edge evidence. "
                          f"{ai_curated} committed record(s) carry evidence, so Layer 4 is a no-op here.")},
            ],
        },

        "provenance": {
            # The legacy vs ai_curated split IS computed (from presence of evidence).
            "measured": True,
            "by_profile": {"legacy": legacy, "ai_curated": ai_curated},
            # Per-record model / prompt-version / run-id / date is NOT captured on
            # records yet, so the model/month rollups cannot be computed.
            "model_provenance_measured": False,
            "by_model": [],
            "by_month": [],
            "note": ("Legacy vs AI-curated split computed from per-edge evidence presence. "
                     "Per-record model/prompt-version/run-id/date is not captured on records "
                     "yet, so by_model / by_month cannot be computed."),
        },

        "indication_coverage": {
            # Coverage = fraction of an EXTERNAL approved-indication list (e.g.
            # DrugCentral / DrugBank) that has a mechanism path. That external
            # denominator is not present in-repo, so the ratio is not computable.
            "measured": False,
            "covered": None,
            "total": None,
            "pct": None,
            # Computable corpus-side facts (the numerator side only):
            "distinct_indications_in_corpus": len(indications),
            "distinct_drugs": len(drug_mesh - {None}),
            "distinct_diseases": len(disease_mesh - {None}),
            "note": ("Coverage vs an external approved-indication list (e.g. DrugCentral) is not "
                     "computed: the external denominator is not in-repo. Only the corpus-side "
                     "counts (distinct indications/drugs/diseases already having a path) are known."),
        },

        "predicate_distribution": {
            "measured": True,
            "total_edges": total_edges,
            "distinct_predicates": len(predicate_counter),
            "top": [{"predicate": p, "count": c}
                    for p, c in predicate_counter.most_common()],
        },

        "path_length_distribution": {
            "measured": True,
            "min": min(link_counts),
            "max": max(link_counts),
            "mean": round(statistics.mean(link_counts), 2),
            "median": statistics.median(link_counts),
            "bins": [{"length": L, "count": length_bins[L]} for L in sorted(length_bins)],
            "in_range_3_7": {"count": in_range, "pct": round(100 * in_range / n, 1) if n else 0},
            "note": "length = number of edges (links) per path; convention target is 3-7.",
        },

        "node_type_coverage": {
            "measured": True,
            "types": [
                {"label": lab, "node_count": node_label_counter[lab],
                 "record_count": len(node_label_records[lab])}
                for lab, _ in node_label_counter.most_common()
            ],
        },

        "structural_quality": {
            "measured": True,
            "summary": {
                "clean": struct_clean,
                "clean_pct": round(100 * struct_clean / n, 1) if n else 0,
                "hard_clean": struct_hard_clean,
                "hard_clean_pct": round(100 * struct_hard_clean / n, 1) if n else 0,
                "hard_flagged": struct_hard,
                "soft_flagged": struct_soft,
                "info_flagged": struct_info,
            },
            "by_code": [
                {"severity": sev, "code": code, "record_count": c}
                for (sev, code), c in sorted(struct_by_code.items(), key=lambda x: -x[1])
            ],
            "polarity": dict(polarity_counter.most_common()),
            "note": ("Deterministic structural scorer (scripts/quality/structural_quality.py). "
                     "record_count = records with >=1 flag of that code."),
        },

        "records_needing_attention": {
            "measured": True,
            "total_flagged": len({it["id"] for it in attention}),
            "total_issues": len(attention),
            "shown": min(len(attention), ATTENTION_LIMIT),
            "items": attention[:ATTENTION_LIMIT],
            "note": ("QC layer failures (schema/ontology/predicate) plus structural HARD/SOFT flags. "
                     f"List capped at {ATTENTION_LIMIT}; total_issues is the full count."),
        },

        "priority_to_curate": {
            # A Dismech-style prioritized worklist of what to (re)curate next needs
            # a work queue seeded from an external approved-indication list; not built.
            "measured": False,
            "items": [],
            "note": ("Prioritized (re)curation worklist needs a work queue seeded from an external "
                     "approved-indication list (e.g. DrugCentral); not computed yet."),
        },
    }
    return dashboard


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=str(DEFAULT_OUT),
                    help=f"Output JSON path (default: {rel(DEFAULT_OUT)})")
    ap.add_argument("--stdout", action="store_true",
                    help="Print JSON to stdout instead of writing the file.")
    args = ap.parse_args()

    print(f"Building dashboard metrics over {PATHS_DIR} …", file=sys.stderr)
    dash = build()
    text = json.dumps(dash, indent=2)

    if args.stdout:
        print(text)
    else:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
        print(f"Wrote {rel(out)} ({len(text)} bytes)", file=sys.stderr)

    # concise human summary to stderr
    t = dash["totals"]
    q = dash["qc_compliance_by_layer"]["layers"]
    s = dash["structural_quality"]["summary"]
    print("\n=== dashboard.json summary ===", file=sys.stderr)
    print(f"  records={t['paths']}  drugs={t['drugs']}  diseases={t['diseases']}  "
          f"avg_len={t['avg_path_length']}", file=sys.stderr)
    for L in q:
        print(f"  QC L{L['layer']} {L['name']:<14} pass={L['pass']} fail={L['fail']}", file=sys.stderr)
    print(f"  structural: clean={s['clean']} ({s['clean_pct']}%)  "
          f"HARD-clean={s['hard_clean']} ({s['hard_clean_pct']}%)  "
          f"HARD-flagged={s['hard_flagged']}  SOFT-flagged={s['soft_flagged']}", file=sys.stderr)
    print(f"  records_needing_attention: {dash['records_needing_attention']['total_flagged']} records / "
          f"{dash['records_needing_attention']['total_issues']} issues", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
