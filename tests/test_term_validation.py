"""Offline tests for scripts/term_validation/.

NO NETWORK. Every backend is driven through a stubbed `_get_json`, so these
tests pin the *decision logic* — which payload means ABSENT, which means
UNRESOLVED — rather than the availability of EBI, NLM or UniProt.

The bulk of this file defends one invariant: a failure to reach an authority
must never be recorded as a term not existing. That is the difference between
"this record cites a fabricated identifier" and "our wifi dropped", and the
whole audit is worthless if it cannot tell them apart.

The payload shapes asserted here were probed against the live APIs on
2026-09-13 and are documented in backends.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from term_validation import backends, resolvers  # noqa: E402
from term_validation.cache import TermCache  # noqa: E402
from term_validation.resolvers import (  # noqa: E402
    Registry, canonical_curie, name_similarity, names_match, normalize_label, uninvert,
)
from term_validation.types import LookupError_, TermResult, TermStatus  # noqa: E402

# Captured before the autouse no-network fixture replaces it, so TestTransport
# can exercise the real transport against a fake urlopen.
_REAL_GET_JSON = backends._get_json


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any backend that reaches for the network without a stub fails loudly."""
    def boom(url, **kw):
        raise AssertionError(f"test tried to hit the network: {url}")
    monkeypatch.setattr(backends, "_get_json", boom)
    backends._ontology_available.clear()
    backends._oak_unavailable.clear()
    backends._oak_adapters.clear()


def stub_http(monkeypatch, responses: dict):
    """Route _get_json by URL substring. Value is (code, payload) or an Exception."""
    def fake(url, **kw):
        for needle, outcome in responses.items():
            if needle in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise AssertionError(f"no stub matched {url}")
    monkeypatch.setattr(backends, "_get_json", fake)


# ── the core invariant ──────────────────────────────────────────────────────
class TestFailureIsNotAbsence:
    def test_network_failure_is_unresolved_not_absent(self, monkeypatch):
        stub_http(monkeypatch, {"uniprotkb": LookupError_("connection reset")})
        result = Registry(config={}, cache=TermCache("/nonexistent"),
                          use_cache=False).resolve("UniProt:P04150")
        assert result.status is TermStatus.UNRESOLVED
        assert result.status is not TermStatus.ABSENT

    def test_unresolved_is_not_a_failure(self):
        assert TermResult("X:1", TermStatus.UNRESOLVED).ok is True
        assert TermResult("X:1", TermStatus.SKIPPED).ok is True

    def test_absent_and_obsolete_are_failures(self):
        assert TermResult("X:1", TermStatus.ABSENT).ok is False
        assert TermResult("X:1", TermStatus.OBSOLETE).ok is False

    def test_unavailable_ontology_cannot_condemn_its_terms(self, monkeypatch):
        """If OLS4 has no such ontology we know nothing about the term.

        Without this guard, one unavailable ontology would mark every term
        under it ABSENT — inventing thousands of failures at once.
        """
        stub_http(monkeypatch, {"/ontologies/pr": (404, None)})
        with pytest.raises(LookupError_):
            backends.resolve_obo("PR:000006147", "pr")

    def test_unexpected_payload_shape_is_unresolved_not_absent(self, monkeypatch):
        stub_http(monkeypatch, {"lookup/details": (200, ["not", "a", "dict"])})
        with pytest.raises(LookupError_):
            backends.resolve_mesh("MESH:D011241")

    def test_missing_terms_key_is_unresolved_not_absent(self, monkeypatch):
        """An empty `terms` list means absent; a MISSING key means the response
        was not what we think it is, which is a different thing entirely."""
        stub_http(monkeypatch, {"lookup/details": (200, {"descriptor": "x"})})
        with pytest.raises(LookupError_):
            backends.resolve_mesh("MESH:D011241")


# ── per-authority not-found signals ─────────────────────────────────────────
class TestMeSH:
    def test_empty_terms_is_absent(self, monkeypatch):
        stub_http(monkeypatch, {"lookup/details": (200, {"terms": [], "qualifiers": []})})
        assert backends.resolve_mesh("MESH:D999999").status is TermStatus.ABSENT

    def test_preferred_term_is_the_label_and_the_rest_are_synonyms(self, monkeypatch):
        stub_http(monkeypatch, {"lookup/details": (200, {"terms": [
            {"label": "Scleroderma, Localized", "preferred": True},
            {"label": "Morphea", "preferred": False},
            {"label": "Dermatosclerosis", "preferred": False},
        ]})})
        r = backends.resolve_mesh("MESH:D012594")
        assert r.status is TermStatus.EXISTS
        assert r.label == "Scleroderma, Localized"
        assert "Morphea" in r.synonyms

    def test_no_preferred_flag_still_yields_a_label(self, monkeypatch):
        stub_http(monkeypatch, {"lookup/details": (200, {"terms": [{"label": "Only Term"}]})})
        assert backends.resolve_mesh("MESH:D1").label == "Only Term"


class TestUniProt:
    def test_404_is_absent(self, monkeypatch):
        stub_http(monkeypatch, {"uniprotkb": (404, None)})
        assert backends.resolve_uniprot("UniProt:Q00000").status is TermStatus.ABSENT

    def test_inactive_entry_is_obsolete_not_absent(self, monkeypatch):
        """A deleted accession resolves but has aged out. Treating it as ABSENT
        would say the curator invented it, which is a different accusation."""
        stub_http(monkeypatch, {"uniprotkb": (200, {
            "entryType": "Inactive",
            "primaryAccession": "X0X0X0",
            "inactiveReason": {"inactiveReasonType": "DELETED"},
        })})
        r = backends.resolve_uniprot("UniProt:X0X0X0")
        assert r.status is TermStatus.OBSOLETE
        assert "DELETED" in (r.detail or "")

    def test_alternative_names_become_synonyms(self, monkeypatch):
        stub_http(monkeypatch, {"uniprotkb": (200, {
            "entryType": "UniProtKB reviewed (Swiss-Prot)",
            "proteinDescription": {
                "recommendedName": {"fullName": {"value": "Glucocorticoid receptor"},
                                    "shortNames": [{"value": "GR"}]},
                "alternativeNames": [{"fullName": {"value": "Nuclear receptor subfamily 3"}}],
            },
        })})
        r = backends.resolve_uniprot("UniProt:P04150")
        assert r.label == "Glucocorticoid receptor"
        assert "GR" in r.synonyms and "Nuclear receptor subfamily 3" in r.synonyms


class TestReactome:
    def test_404_is_absent(self, monkeypatch):
        stub_http(monkeypatch, {"ContentService": (404, None)})
        assert backends.resolve_reactome("REACT:R-HSA-999999").status is TermStatus.ABSENT

    def test_display_name_is_the_label(self, monkeypatch):
        stub_http(monkeypatch, {"ContentService": (200, {"displayName": "NE Release Cycle"})})
        assert backends.resolve_reactome("REACT:R-HSA-181430").label == "NE Release Cycle"


class TestOLS:
    def test_empty_terms_is_absent_once_ontology_confirmed(self, monkeypatch):
        stub_http(monkeypatch, {"/ontologies/go/terms": (200, {"_embedded": {"terms": []}}),
                                "/ontologies/go": (200, {"ontologyId": "go"})})
        assert backends.resolve_obo("GO:0000000", "go").status is TermStatus.ABSENT

    def test_is_obsolete_flag_is_obsolete(self, monkeypatch):
        stub_http(monkeypatch, {"/ontologies/go/terms": (200, {"_embedded": {"terms": [
            {"label": "obsolete toxin transport", "is_obsolete": True}]}}),
            "/ontologies/go": (200, {"ontologyId": "go"})})
        assert backends.resolve_obo("GO:1901998", "go").status is TermStatus.OBSOLETE

    def test_synonyms_are_captured(self, monkeypatch):
        stub_http(monkeypatch, {"/ontologies/go/terms": (200, {"_embedded": {"terms": [
            {"label": "inflammatory response", "synonyms": ["inflammation"]}]}}),
            "/ontologies/go": (200, {"ontologyId": "go"})})
        assert "inflammation" in backends.resolve_obo("GO:0006954", "go").synonyms


# ── prefix aliasing ─────────────────────────────────────────────────────────
class TestPrefixAliasing:
    def test_legacy_taxonomy_prefix_is_canonicalised_for_lookup(self):
        assert canonical_curie("taxonomy:10298") == "NCBITaxon:10298"
        assert canonical_curie("reactome:R-HSA-1") == "REACT:R-HSA-1"

    def test_unaliased_prefixes_pass_through(self):
        assert canonical_curie("GO:0006954") == "GO:0006954"

    def test_result_is_reported_under_the_corpus_spelling(self, monkeypatch):
        """The corpus keeps `taxonomy:`; we translate only to ask the question.

        Regression guard: querying OLS4 with the corpus spelling returns nothing
        and would have marked all 166 taxonomy nodes ABSENT.
        """
        stub_http(monkeypatch, {
            "/ontologies/ncbitaxon/terms": (200, {"_embedded": {"terms": [
                {"label": "Human alphaherpesvirus 1"}]}}),
            "/ontologies/ncbitaxon": (200, {"ontologyId": "ncbitaxon"}),
        })
        reg = Registry(config={"taxonomy": "sqlite:obo:ncbitaxon"},
                       cache=TermCache("/nonexistent"), prefer_oak=False, use_cache=False)
        r = reg.resolve("taxonomy:10298")
        assert r.status is TermStatus.EXISTS
        assert r.curie == "taxonomy:10298"


# ── routing policy ──────────────────────────────────────────────────────────
class TestPolicy:
    def _reg(self, config):
        return Registry(config=config, cache=TermCache("/nonexistent"), use_cache=False)

    def test_empty_adapter_without_custom_resolver_is_skipped(self):
        reg = self._reg({"InterPro": ""})
        assert reg.resolve("InterPro:IPR001796").status is TermStatus.SKIPPED

    def test_empty_adapter_with_custom_resolver_still_validates(self, monkeypatch):
        """conf/oak_config.yaml sets MESH to "" meaning "not OAK's job", not
        "do not validate" — its own comments say a custom validator handles it."""
        stub_http(monkeypatch, {"lookup/details": (200, {"terms": [
            {"label": "Prednisone", "preferred": True}]})})
        reg = self._reg({"MESH": ""})
        assert reg.resolve("MESH:D011241").status is TermStatus.EXISTS

    def test_unlisted_prefix_is_skipped_not_failed(self):
        reg = self._reg({})
        r = reg.resolve("WEIRD:123")
        assert r.status is TermStatus.SKIPPED
        assert "not listed" in (r.detail or "")

    def test_non_curie_is_unresolved(self):
        assert self._reg({}).resolve("no-colon-here").status is TermStatus.UNRESOLVED

    def test_offline_never_touches_the_network(self):
        reg = Registry(config={"GO": "sqlite:obo:go"}, cache=TermCache("/nonexistent"),
                       offline=True, use_cache=False)
        r = reg.resolve("GO:0006954")
        assert r.status is TermStatus.UNRESOLVED
        assert "offline" in (r.detail or "")


# ── cache ───────────────────────────────────────────────────────────────────
class TestCache:
    def test_round_trip(self, tmp_path):
        cache = TermCache(tmp_path)
        cache.put(TermResult("GO:1", TermStatus.EXISTS, label="thing",
                             source="ols4:go", synonyms=("other",)))
        cache.flush()
        got = TermCache(tmp_path).get("GO:1")
        assert got.status is TermStatus.EXISTS
        assert got.label == "thing"
        assert got.synonyms == ("other",)

    def test_transient_states_are_never_cached(self, tmp_path):
        """Caching UNRESOLVED would make a momentary outage a permanent fact."""
        cache = TermCache(tmp_path)
        cache.put(TermResult("GO:2", TermStatus.UNRESOLVED, detail="timeout"))
        cache.put(TermResult("GO:3", TermStatus.SKIPPED))
        cache.flush()
        assert TermCache(tmp_path).get("GO:2") is None
        assert TermCache(tmp_path).get("GO:3") is None

    def test_absent_and_obsolete_are_cached(self, tmp_path):
        cache = TermCache(tmp_path)
        cache.put(TermResult("GO:4", TermStatus.ABSENT))
        cache.put(TermResult("GO:5", TermStatus.OBSOLETE, label="old"))
        cache.flush()
        assert TermCache(tmp_path).get("GO:4").status is TermStatus.ABSENT
        assert TermCache(tmp_path).get("GO:5").status is TermStatus.OBSOLETE

    def test_shards_are_per_prefix(self, tmp_path):
        cache = TermCache(tmp_path)
        cache.put(TermResult("GO:1", TermStatus.EXISTS))
        cache.put(TermResult("MESH:D1", TermStatus.EXISTS))
        cache.flush()
        assert (tmp_path / "GO.json").exists() and (tmp_path / "MESH.json").exists()

    def test_corrupt_shard_is_reported_not_swallowed(self, tmp_path):
        (tmp_path / "GO.json").write_text("{ this is not json")
        with pytest.raises(ValueError, match="not valid JSON"):
            TermCache(tmp_path).get("GO:1")

    def test_cache_hit_short_circuits_the_backend(self, tmp_path):
        cache = TermCache(tmp_path)
        cache.put(TermResult("GO:9", TermStatus.EXISTS, label="cached"))
        cache.flush()
        # _no_network would raise if a backend were reached.
        reg = Registry(config={"GO": "sqlite:obo:go"}, cache=TermCache(tmp_path))
        assert reg.resolve("GO:9").label == "cached"
        assert reg.stats["cache_hits"] == 1


# ── name matching ───────────────────────────────────────────────────────────
class TestNameMatching:
    def _exists(self, label, synonyms=()):
        return TermResult("X:1", TermStatus.EXISTS, label=label, synonyms=tuple(synonyms))

    def test_exact_and_case_and_spacing(self):
        assert names_match("Inflammatory Response", self._exists("inflammatory response"))
        assert names_match("inflammatory  response", self._exists("inflammatory response"))

    def test_synonym_is_accepted(self):
        assert names_match("Morphea", self._exists("Scleroderma, Localized", ["Morphea"]))

    def test_mesh_inverted_heading_is_accepted(self):
        """MeSH inverts headings as a house style; flagging that would bury the
        real mismatches under ~2,500 formatting complaints."""
        assert names_match("Rheumatoid arthritis", self._exists("Arthritis, Rheumatoid"))
        assert names_match("Cutaneous T-Cell Lymphoma",
                           self._exists("Lymphoma, T-Cell, Cutaneous"))

    def test_genuinely_wrong_name_is_flagged(self):
        assert not names_match("Banana ripening factor 7",
                               self._exists("Amine oxidase [flavin-containing] A"))

    def test_absent_name_is_not_a_mismatch(self):
        assert names_match(None, self._exists("anything"))
        assert names_match("", self._exists("anything"))

    def test_uninvert(self):
        assert uninvert("Arthritis, Rheumatoid") == "Rheumatoid Arthritis"
        assert uninvert("Lymphoma, T-Cell, Cutaneous") == "Cutaneous T-Cell Lymphoma"
        assert uninvert("No commas here") == "No commas here"

    def test_similarity_ranks_but_does_not_decide(self):
        assert name_similarity("Banana factor", "Amine oxidase") == 0.0
        assert name_similarity("inflammatory response", "inflammatory response") == 1.0
        assert 0 < name_similarity("Juvenile idiopathic arthritis", "Arthritis, Juvenile") < 1

    def test_normalize_label_is_conservative(self):
        """It absorbs case and spacing only — stripping punctuation would start
        hiding real mismatches."""
        assert normalize_label("  A  B ") == "a b"
        assert normalize_label("4-Aminobenzoic Acid") != normalize_label("Aminobenzoic Acid")


# ── config ──────────────────────────────────────────────────────────────────
class TestConfig:
    def test_reads_the_repo_config(self):
        cfg = resolvers.load_config()
        assert cfg["GO"] == "sqlite:obo:go"
        assert cfg["MESH"] == ""          # not OAK's job; custom validator handles it

    def test_ontology_name_extraction(self):
        assert resolvers.ontology_name("sqlite:obo:go") == "go"
        assert resolvers.ontology_name("") is None
        assert resolvers.ontology_name("ols:") is None

    def test_missing_config_raises(self):
        with pytest.raises(FileNotFoundError):
            resolvers.load_config("/nope/oak_config.yaml")

    def test_malformed_config_raises(self, tmp_path):
        bad = tmp_path / "c.yaml"
        bad.write_text(json.dumps({"ontology_adapters": "not a mapping"}))
        with pytest.raises(ValueError, match="ontology_adapters"):
            resolvers.load_config(bad)

    def test_every_configured_obo_prefix_is_reachable_policy(self):
        """Guard against a config edit that silently stops validating a prefix."""
        reg = Registry(cache=TermCache("/nonexistent"), use_cache=False)
        for prefix in ("GO", "HP", "CL", "UBERON", "CHEBI", "NCBITaxon"):
            kind, _ = reg.policy_for(prefix)
            assert kind == "obo", f"{prefix} stopped being validated"
        for prefix in ("MESH", "UniProt", "reactome"):
            kind, _ = reg.policy_for(prefix)
            assert kind == "custom", f"{prefix} stopped being validated"


# ── the audit walker ────────────────────────────────────────────────────────
class _FakeRegistry:
    """Registry stand-in returning canned results, so the walker is tested
    independently of any backend or network."""

    def __init__(self, results: dict):
        self.results = results
        self.stats = {"cache_hits": 0, "lookups": 0}

    def resolve(self, curie):
        return self.results.get(curie, TermResult(curie, TermStatus.SKIPPED))

    def flush(self):
        return []


def _write_record(tmp_path, name, nodes):
    import yaml as _yaml
    p = tmp_path / name
    p.write_text(_yaml.safe_dump({
        "directed": True, "multigraph": True,
        "graph": {"_id": name.replace(".yaml", "")},
        "nodes": nodes, "links": [],
    }))
    return p


class TestAuditWalker:
    def test_counts_occurrences_but_reports_distinct_curies(self, tmp_path):
        """One fabricated id reused across 3 records is ONE problem, not three."""
        from term_validation.audit import audit
        files = [_write_record(tmp_path, f"r{i}.yaml",
                               [{"id": "GO:0000000", "label": "BiologicalProcess", "name": "x"}])
                 for i in range(3)]
        reg = _FakeRegistry({"GO:0000000": TermResult("GO:0000000", TermStatus.ABSENT)})
        rep = audit(files, reg)
        assert rep.nodes_checked == 3
        assert rep.unique_curies == 1
        assert len(rep.existence_failures) == 1
        assert rep.status_counts["absent"] == 3

    def test_unresolved_produces_no_finding(self, tmp_path):
        from term_validation.audit import audit
        f = _write_record(tmp_path, "r.yaml",
                          [{"id": "PR:1", "label": "MacromolecularComplex", "name": "x"}])
        reg = _FakeRegistry({"PR:1": TermResult("PR:1", TermStatus.UNRESOLVED, detail="down")})
        rep = audit([f], reg)
        assert rep.findings == []
        assert rep.status_counts["unresolved"] == 1

    def test_existence_and_name_findings_are_separate_kinds(self, tmp_path):
        from term_validation.audit import audit
        f = _write_record(tmp_path, "r.yaml", [
            {"id": "GO:0000000", "label": "BiologicalProcess", "name": "ghost"},
            {"id": "GO:0006954", "label": "BiologicalProcess", "name": "Banana factor"},
        ])
        reg = _FakeRegistry({
            "GO:0000000": TermResult("GO:0000000", TermStatus.ABSENT),
            "GO:0006954": TermResult("GO:0006954", TermStatus.EXISTS,
                                     label="inflammatory response"),
        })
        rep = audit([f], reg)
        assert len(rep.existence_failures) == 1
        assert len(rep.name_mismatches) == 1

    def test_a_matching_synonym_produces_no_name_finding(self, tmp_path):
        from term_validation.audit import audit
        f = _write_record(tmp_path, "r.yaml",
                          [{"id": "MESH:D1", "label": "Disease", "name": "Morphea"}])
        reg = _FakeRegistry({"MESH:D1": TermResult(
            "MESH:D1", TermStatus.EXISTS, label="Scleroderma, Localized",
            synonyms=("Morphea",))})
        assert audit([f], reg).name_mismatches == []

    def test_names_skipped_when_disabled(self, tmp_path):
        from term_validation.audit import audit
        f = _write_record(tmp_path, "r.yaml",
                          [{"id": "GO:1", "label": "BiologicalProcess", "name": "wrong"}])
        reg = _FakeRegistry({"GO:1": TermResult("GO:1", TermStatus.EXISTS, label="right")})
        assert audit([f], reg, check_names=False).name_mismatches == []

    def test_existence_sorts_before_names_and_names_by_similarity(self, tmp_path):
        from term_validation.audit import audit
        f = _write_record(tmp_path, "r.yaml", [
            {"id": "GO:1", "label": "BiologicalProcess", "name": "inflammatory answer"},
            {"id": "GO:2", "label": "BiologicalProcess", "name": "totally unrelated words"},
            {"id": "GO:3", "label": "BiologicalProcess", "name": "ghost"},
        ])
        reg = _FakeRegistry({
            "GO:1": TermResult("GO:1", TermStatus.EXISTS, label="inflammatory response"),
            "GO:2": TermResult("GO:2", TermStatus.EXISTS, label="inflammatory response"),
            "GO:3": TermResult("GO:3", TermStatus.ABSENT),
        })
        kinds = [f.kind for f in audit([f], reg).findings]
        assert kinds[0] == "existence"
        names = [x for x in audit([f], reg).findings if x.kind == "name"]
        assert names[0].similarity <= names[-1].similarity

    def test_obsolete_is_an_existence_finding(self, tmp_path):
        from term_validation.audit import audit
        f = _write_record(tmp_path, "r.yaml",
                          [{"id": "GO:1901998", "label": "BiologicalProcess", "name": "toxin transport"}])
        reg = _FakeRegistry({"GO:1901998": TermResult(
            "GO:1901998", TermStatus.OBSOLETE, label="obsolete toxin transport")})
        rep = audit([f], reg)
        assert len(rep.existence_failures) == 1
        assert rep.existence_failures[0].result.status is TermStatus.OBSOLETE

    def test_malformed_nodes_are_skipped_not_crashed(self, tmp_path):
        from term_validation.audit import audit
        import yaml as _yaml
        p = tmp_path / "bad.yaml"
        p.write_text(_yaml.safe_dump({"nodes": ["not a mapping", {"no_id": 1},
                                                {"id": 123}, {"id": "GO:1", "name": "ok"}]}))
        reg = _FakeRegistry({"GO:1": TermResult("GO:1", TermStatus.EXISTS, label="ok")})
        assert audit([p], reg).nodes_checked == 1

    def test_report_serialises(self, tmp_path):
        from term_validation.audit import audit
        f = _write_record(tmp_path, "r.yaml",
                          [{"id": "GO:0000000", "label": "BiologicalProcess", "name": "x"}])
        reg = _FakeRegistry({"GO:0000000": TermResult("GO:0000000", TermStatus.ABSENT)})
        d = audit([f], reg).to_dict()
        json.dumps(d)  # must be JSON-clean for the committed report
        assert d["existence_failure_count"] == 1
        assert d["prefix_status"]["GO"]["absent"] == 1


# ── HTTP transport ──────────────────────────────────────────────────────────
class TestTransport:
    """_get_json is where a transport problem could become a false ABSENT, so
    its status handling is pinned here rather than trusted."""

    def _urlopen(self, monkeypatch, sequence):
        """Feed urlopen a sequence of (body, code) or Exception."""
        import urllib.request as _req
        calls = {"n": 0}

        class _Resp:
            def __init__(self, body, code):
                self._body, self._code = body, code
            def read(self):
                return self._body.encode()
            def getcode(self):
                return self._code
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake(req, **kw):
            item = sequence[min(calls["n"], len(sequence) - 1)]
            calls["n"] += 1
            if isinstance(item, Exception):
                raise item
            return _Resp(*item)

        monkeypatch.setattr(_req, "urlopen", fake)
        monkeypatch.setattr(backends.time, "sleep", lambda *_: None)
        monkeypatch.setattr(backends, "_last_call_by_host", {})
        return calls

    def test_404_is_data_not_an_error(self, monkeypatch):
        import urllib.error
        self._urlopen(monkeypatch, [urllib.error.HTTPError("u", 404, "nf", {}, None)])
        assert _REAL_GET_JSON("https://x/y") == (404, None)

    def test_retryable_status_is_retried_then_succeeds(self, monkeypatch):
        import urllib.error
        calls = self._urlopen(monkeypatch, [
            urllib.error.HTTPError("u", 503, "busy", {}, None),
            ('{"ok": true}', 200),
        ])
        assert _REAL_GET_JSON("https://x/y") == (200, {"ok": True})
        assert calls["n"] == 2

    def test_non_retryable_status_raises_immediately(self, monkeypatch):
        import urllib.error
        calls = self._urlopen(monkeypatch, [urllib.error.HTTPError("u", 403, "no", {}, None)])
        with pytest.raises(LookupError_, match="403"):
            _REAL_GET_JSON("https://x/y")
        assert calls["n"] == 1

    def test_persistent_network_error_raises_after_max_attempts(self, monkeypatch):
        import urllib.error
        calls = self._urlopen(monkeypatch, [urllib.error.URLError("down")])
        with pytest.raises(LookupError_, match="network error"):
            _REAL_GET_JSON("https://x/y")
        assert calls["n"] == backends._MAX_ATTEMPTS

    def test_empty_body_raises(self, monkeypatch):
        self._urlopen(monkeypatch, [("   ", 200)])
        with pytest.raises(LookupError_, match="empty body"):
            _REAL_GET_JSON("https://x/y")

    def test_non_json_body_raises(self, monkeypatch):
        self._urlopen(monkeypatch, [("<html>nope</html>", 200)])
        with pytest.raises(LookupError_, match="non-JSON"):
            _REAL_GET_JSON("https://x/y")


class TestOakFallback:
    def test_failed_adapter_build_is_remembered(self, monkeypatch):
        """Building an OAK adapter downloads a large database. Retrying a build
        that already failed would repeat that for every term in the corpus."""
        attempts = {"n": 0}

        def fake_get_adapter(_s):
            attempts["n"] += 1
            raise RuntimeError("bucket returned 403")

        import oaklib
        monkeypatch.setattr(oaklib, "get_adapter", fake_get_adapter)
        for _ in range(5):
            with pytest.raises(LookupError_):
                backends.resolve_oak("GO:1", "sqlite:obo:go")
        assert attempts["n"] == 1

    def test_registry_falls_back_from_oak_to_ols(self, monkeypatch):
        """An unreachable OAK adapter must not become evidence about the term."""
        import oaklib
        monkeypatch.setattr(oaklib, "get_adapter",
                            lambda _s: (_ for _ in ()).throw(RuntimeError("403")))
        stub_http(monkeypatch, {
            "/ontologies/go/terms": (200, {"_embedded": {"terms": [
                {"label": "inflammatory response"}]}}),
            "/ontologies/go": (200, {"ontologyId": "go"}),
        })
        reg = Registry(config={"GO": "sqlite:obo:go"}, cache=TermCache("/nonexistent"),
                       prefer_oak=True, use_cache=False)
        r = reg.resolve("GO:0006954")
        assert r.status is TermStatus.EXISTS
        assert r.source == "ols4:go"

    def test_oak_absence_requires_confirmation_not_a_null_label(self, monkeypatch):
        """adapter.label() returns None for both 'absent' and 'present but
        unlabelled', so absence is only recorded after checking entities()."""
        class _Adapter:
            def label(self, _c):
                return None
            def entities(self):
                return ["GO:0006954"]

        import oaklib
        monkeypatch.setattr(oaklib, "get_adapter", lambda _s: _Adapter())
        present = backends.resolve_oak("GO:0006954", "sqlite:obo:go")
        assert present.status is TermStatus.EXISTS
        backends._oak_adapters.clear()
        monkeypatch.setattr(oaklib, "get_adapter", lambda _s: _Adapter())
        missing = backends.resolve_oak("GO:0000000", "sqlite:obo:go")
        assert missing.status is TermStatus.ABSENT

    def test_oak_entities_failure_is_unresolved_not_absent(self, monkeypatch):
        class _Adapter:
            def label(self, _c):
                return None
            def entities(self):
                raise RuntimeError("db locked")

        import oaklib
        monkeypatch.setattr(oaklib, "get_adapter", lambda _s: _Adapter())
        with pytest.raises(LookupError_, match="could not confirm absence"):
            backends.resolve_oak("GO:1", "sqlite:obo:go")

    def test_cache_is_flushed_periodically(self, tmp_path, monkeypatch):
        """A full-corpus pass is ~5,100 lookups over hours; without incremental
        flushing a late crash loses every resolution."""
        from term_validation.audit import audit
        files = [_write_record(tmp_path, f"r{i}.yaml",
                               [{"id": f"GO:{i}", "label": "BiologicalProcess", "name": "x"}])
                 for i in range(10)]
        flushes = {"n": 0}

        class _Reg(_FakeRegistry):
            def flush(self):
                flushes["n"] += 1
                return []

        reg = _Reg({f"GO:{i}": TermResult(f"GO:{i}", TermStatus.EXISTS, label="x")
                    for i in range(10)})
        audit(files, reg, flush_every=3)
        assert flushes["n"] == 3          # at 3, 6, 9

    def test_flush_every_zero_disables_incremental_flushing(self, tmp_path):
        from term_validation.audit import audit
        files = [_write_record(tmp_path, "r.yaml",
                               [{"id": "GO:1", "label": "BiologicalProcess", "name": "x"}])]
        flushes = {"n": 0}

        class _Reg(_FakeRegistry):
            def flush(self):
                flushes["n"] += 1
                return []

        audit(files, _Reg({"GO:1": TermResult("GO:1", TermStatus.EXISTS, label="x")}),
              flush_every=0)
        assert flushes["n"] == 0
