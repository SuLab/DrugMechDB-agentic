"""
Tests for the source-agnostic evidence-fetch layer (scripts/evidence_sources/).

The load-bearing contracts:
  1. Cache keying is byte-identical to what QC Layer 4's validator computes, for
     every source — so a snippet is checked against exactly the file the fetcher
     wrote (this is what makes Layer 4 source-agnostic).
  2. The cache shape matches pubmed_fetch's, so the QC gate treats every source
     uniformly.
  3. A snippet copied from a written cache validates under the real Layer 4 matcher.
  4. Ephemeral full text: a non-PubMed full_text cache reverts to abstract-only,
     keeping the snippet + metadata but deleting the body.

Parsing tests monkeypatch the shared HTTP boundary with recorded responses, so
they are offline/deterministic. Live tests are gated on DMDB_NETWORK_TESTS=1.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evidence_sources import (  # noqa: E402
    common, get_source, sources, strip_all_fulltext,
    ChEMBLSource, ClinicalTrialsSource, BioRxivSource, MedRxivSource,
    PubMedSource,
)

# The real Layer-4 matcher + the validator's own cache-key logic.
from linkml_reference_validator.validation.supporting_text_validator import (  # noqa: E402
    SupportingTextValidator,
)
from linkml_reference_validator.models import ReferenceValidationConfig  # noqa: E402
from linkml_reference_validator.etl.reference_fetcher import ReferenceFetcher  # noqa: E402

norm = SupportingTextValidator.normalize_text

# pubmed_fetch, loaded the same way so shape-parity compares like with like.
_pf_spec = importlib.util.spec_from_file_location("pubmed_fetch_test", SCRIPTS / "pubmed_fetch.py")
pf = importlib.util.module_from_spec(_pf_spec)
_pf_spec.loader.exec_module(pf)


def _matches(snippet: str, body: str) -> bool:
    return norm(snippet) in norm(body)


# ─── 1. cache-key parity with the QC validator ───────────────────────────────

@pytest.mark.parametrize("ref", [
    "PMID:35569550", "ChEMBL:CHEMBL25", "chembl:CHEMBL25",
    "bioRxiv:10.1101/2020.05.01.072066", "medRxiv:10.1101/2021.01.01.21249100",
    "clinicaltrials:NCT00000102",
])
def test_cache_key_matches_validator(ref):
    vf = ReferenceFetcher(ReferenceValidationConfig())
    validator_name = vf.get_cache_path(vf.normalize_reference_id(ref)).name
    assert common.cache_filename(ref) == validator_name


# ─── 2. cache-shape parity with pubmed_fetch ─────────────────────────────────

def test_write_cache_shape_matches_pubmed(tmp_path, monkeypatch):
    record = {"title": "A study", "authors": ["Doe J"], "journal": "J",
              "year": "2020", "abstract": "The drug decreases activity of the target."}
    # pubmed_fetch writes PMID_999.md; our writer writes the same for reference PMID:999.
    monkeypatch.setattr(pf, "CACHE_DIR", tmp_path)
    pf_path = pf._write_cache("999", dict(record), content_type="abstract")
    our_path = common.write_cache("PMID:999", dict(record), content_type="abstract",
                                  cache_dir=tmp_path / "ours")

    # Both load through the validator to the SAME content + title (uniform to QC).
    la = ReferenceFetcher(ReferenceValidationConfig(cache_dir=tmp_path))._load_from_disk("PMID:999")
    lb = ReferenceFetcher(ReferenceValidationConfig(cache_dir=tmp_path / "ours"))._load_from_disk("PMID:999")
    assert la is not None and lb is not None
    assert la.content == lb.content
    assert la.title == lb.title
    assert "## Content" in pf_path.read_text() and "## Content" in our_path.read_text()


def test_content_type_roundtrip_and_marker(tmp_path):
    p = common.write_cache("ChEMBL:CHEMBL25", {"title": "T", "abstract": "x"},
                           content_type="abstract", cache_dir=tmp_path)
    assert common.cache_content_type(p) == "abstract"
    body = common.assemble_fulltext_body("the abstract sentence", "the full body sentence")
    p2 = common.write_cache("ChEMBL:CHEMBL25", {"title": "T"}, content_type="full_text",
                            body=body, cache_dir=tmp_path)
    assert common.cache_content_type(p2) == "full_text"
    assert common.FULLTEXT_MARKER in p2.read_text()


# ─── 3. dispatch + identity ──────────────────────────────────────────────────

def test_dispatch_by_prefix():
    assert isinstance(get_source("ChEMBL:CHEMBL25"), ChEMBLSource)
    assert isinstance(get_source("chembl:CHEMBL25"), ChEMBLSource)  # case-insensitive
    assert isinstance(get_source("clinicaltrials:NCT00000102"), ClinicalTrialsSource)
    assert isinstance(get_source("NCT00000102"), ClinicalTrialsSource)  # bare NCT
    assert isinstance(get_source("bioRxiv:10.1101/x"), BioRxivSource)
    assert isinstance(get_source("medRxiv:10.1101/x"), MedRxivSource)
    assert isinstance(get_source("PMID:123"), PubMedSource)
    assert isinstance(get_source("123"), PubMedSource)  # bare digits -> PubMed
    assert get_source("bogus:xyz") is None


def test_canonical_reference():
    assert ChEMBLSource().canonical_reference("CHEMBL25") == "ChEMBL:CHEMBL25"
    assert ChEMBLSource().canonical_reference("ChEMBL:CHEMBL25") == "ChEMBL:CHEMBL25"
    assert ClinicalTrialsSource().canonical_reference("nct00000102") == "clinicaltrials:NCT00000102"


def test_sources_listing_nonempty():
    prefixes = {s.PREFIX for s in sources()}
    assert {"PMID", "ChEMBL", "clinicaltrials", "bioRxiv", "medRxiv"} <= prefixes


# ─── 4. per-source parsing against recorded responses (offline) ──────────────

CHEMBL_JSON = json.dumps({"mechanisms": [
    {"mechanism_of_action": "Cyclooxygenase inhibitor", "target_chembl_id": "CHEMBL2094253",
     "mechanism_comment": None}]}).encode()
MOLECULE_JSON = json.dumps({"pref_name": "ASPIRIN"}).encode()


def test_chembl_parses_and_layer4(tmp_path, monkeypatch):
    def fake_get(url, **kw):
        return MOLECULE_JSON if "/molecule/" in url else CHEMBL_JSON
    monkeypatch.setattr(common, "http_get", fake_get)
    res = ChEMBLSource().fetch("ChEMBL:CHEMBL25", cache_dir=tmp_path, force=True)
    assert res["path"] and not res.get("error")
    body = Path(res["path"]).read_text()
    assert _matches("Cyclooxygenase inhibitor", body)   # the assertion is snippet-able


CT_JSON = json.dumps({"protocolSection": {
    "identificationModule": {"officialTitle": "A trial", "nctId": "NCT00000102"},
    "descriptionModule": {"briefSummary": "Nifedipine reduces ACTH levels in patients.",
                          "detailedDescription": "Long description here about the axis."},
    "statusModule": {"overallStatus": "COMPLETED", "statusVerifiedDate": "2004-01"}}}).encode()


def test_clinicaltrials_parses_and_layer4(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "http_get", lambda url, **kw: CT_JSON)
    res = ClinicalTrialsSource().fetch("clinicaltrials:NCT00000102", cache_dir=tmp_path, force=True)
    assert res["path"] and not res.get("error")
    body = Path(res["path"]).read_text()
    assert _matches("Nifedipine reduces ACTH levels in patients", body)


BIORXIV_DETAILS = json.dumps({"collection": [{
    "title": "A preprint", "authors": "Doe, J.; Roe, R.", "doi": "10.1101/2020.05.01.072066",
    "date": "2020-05-01", "license": "cc_by", "abstract": "The drug inhibits the enzyme.",
    "jatsxml": "https://www.biorxiv.org/content/x.source.xml"}]}).encode()

JATS = b"""<?xml version="1.0"?>
<article><body><sec><title>Results</title>
<p>The preprint body states the enzyme is strongly inhibited by the drug in cells.</p>
<p>This inhibition was dose dependent across the concentration range tested and was
reproduced in three independent biological replicates using orthogonal assays, which
together establish that the compound acts directly on the enzyme rather than through
an off-target mechanism, consistent with the abstract summary.</p>
</sec></body></article>"""


def test_biorxiv_abstract_and_ephemeral_fulltext(tmp_path, monkeypatch):
    def fake_get(url, **kw):
        return JATS if url.endswith(".source.xml") else BIORXIV_DETAILS
    monkeypatch.setattr(common, "http_get", fake_get)
    src = BioRxivSource()
    ref = "bioRxiv:10.1101/2020.05.01.072066"

    # abstract tier
    res = src.fetch(ref, cache_dir=tmp_path, force=True)
    assert res["path"] and not res.get("error")
    assert common.cache_content_type(Path(res["path"])) == "abstract"

    # escalate to full text (ephemeral)
    ft = src.fetch_fulltext(ref, cache_dir=tmp_path, force=True)
    assert ft.get("content_type") == "full_text"
    p = Path(ft["path"])
    body = p.read_text()
    assert _matches("strongly inhibited by the drug in cells", body)  # full-text-only sentence
    assert _matches("The drug inhibits the enzyme", body)             # abstract still present

    # strip -> body deleted, abstract + metadata kept, content_type reverts
    out = strip_all_fulltext(cache_dir=tmp_path)
    assert any(r.get("stripped") for r in out)
    after = p.read_text()
    assert common.cache_content_type(p) == "abstract"
    assert common.FULLTEXT_MARKER not in after
    assert _matches("The drug inhibits the enzyme", after)                 # kept
    assert not _matches("strongly inhibited by the drug in cells", after)  # ephemeral, gone
    assert len(after) < len(body)


# ─── 5. live smoke tests (opt-in: DMDB_NETWORK_TESTS=1) ──────────────────────

NETWORK = os.environ.get("DMDB_NETWORK_TESTS") == "1"
net = pytest.mark.skipif(not NETWORK, reason="set DMDB_NETWORK_TESTS=1 to run network tests")


@net
def test_live_chembl(tmp_path):
    res = ChEMBLSource().fetch("ChEMBL:CHEMBL25", cache_dir=tmp_path, force=True)
    assert not res.get("error")
    assert _matches("Cyclooxygenase inhibitor", Path(res["path"]).read_text())


@net
def test_live_clinicaltrials(tmp_path):
    res = ClinicalTrialsSource().fetch("clinicaltrials:NCT00000102", cache_dir=tmp_path, force=True)
    assert not res.get("error")
    assert "## Content" in Path(res["path"]).read_text()


@net
def test_live_biorxiv_fulltext_then_strip(tmp_path):
    ref = "bioRxiv:10.1101/2020.05.01.072066"
    ft = BioRxivSource().fetch_fulltext(ref, cache_dir=tmp_path, force=True)
    assert ft.get("content_type") == "full_text", ft
    p = Path(ft["path"])
    assert common.cache_content_type(p) == "full_text"
    strip_all_fulltext(cache_dir=tmp_path)
    assert common.cache_content_type(p) == "abstract"
    assert common.FULLTEXT_MARKER not in p.read_text()
