"""
Full-text tier tests — the JATS/BioC normalization contract and probe/fetch.

The load-bearing property: a sentence the agent copies out of the normalized
cache body must survive `linkml-reference-validator`'s own normalization as a
substring (Layer 4). These tests assert that contract directly against the
upstream validator's `normalize_text`, plus the section-exclusion guarantees
(no bibliography / no raw table cells / no injected citation markers).

Network-touching tests (probe, fetch_fulltext) are skipped unless
DMDB_NETWORK_TESTS=1, so CI stays offline and deterministic.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "pubmed_fetch.py"

# Import the script as a module without requiring a package.
_spec = importlib.util.spec_from_file_location("pubmed_fetch", SCRIPT)
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)

# The real Layer-4 matcher's normalization — the thing our snippets must satisfy.
from linkml_reference_validator.validation.supporting_text_validator import (  # noqa: E402
    SupportingTextValidator,
)

norm = SupportingTextValidator.normalize_text


def _matches(snippet: str, body: str) -> bool:
    """True if `snippet` would validate as a substring of `body` under Layer 4."""
    return norm(snippet) in norm(body)


# A JATS sample exercising: a soft-wrap hyphen, an inline <xref> citation marker,
# <sub> subscripts, a Greek entity, a kept table CAPTION, dropped table CELLS,
# a dropped <front> abstract, and a dropped <back>/<ref-list> bibliography.
JATS_SAMPLE = b"""<?xml version="1.0"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS" "JATS.dtd">
<article>
  <front>
    <article-meta>
      <title-group><article-title>Aspirin mechanism</article-title></title-group>
      <abstract><p>ABSTRACTONLYTOKEN should be dropped from body normalization.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Mechanism</title>
      <p>Aspirin irreversibly acetylates cyclo-
oxygenase 1 (COX-1)<xref ref-type="bibr" rid="b1">12</xref> and thereby reduces prostaglandin synthesis.</p>
      <p>The H<sub>2</sub>O<sub>2</sub> level and &alpha;-tubulin were measured.</p>
    </sec>
    <table-wrap>
      <caption><p>Table 1. Summary of effects.</p></caption>
      <table><tr><td>9999</td><td>8888</td></tr></table>
    </table-wrap>
  </body>
  <back>
    <ref-list>
      <ref id="b1"><element-citation>BIBLIOGRAPHYTOKEN cardiovascular study</element-citation></ref>
    </ref-list>
  </back>
</article>
"""

BIOC_SAMPLE = b"""<?xml version="1.0"?>
<collection>
  <document>
    <id>12345</id>
    <passage>
      <infon key="section_type">TITLE</infon>
      <text>A study of aspirin and COX-1 inhibition.</text>
    </passage>
    <passage>
      <infon key="section_type">RESULTS</infon>
      <text>Aspirin reduced prostaglandin synthesis significantly in the cohort.</text>
    </passage>
    <passage>
      <infon key="section_type">REF</infon>
      <text>BIOCREFTOKEN smith et al 2020</text>
    </passage>
  </document>
</collection>
"""


# ─── normalize_jats ────────────────────────────────────────────────────────

def test_jats_body_sentence_matches_validator():
    body = pf.normalize_jats(JATS_SAMPLE)
    # The core mechanistic sentence validates as a Layer-4 substring.
    assert _matches("Aspirin irreversibly acetylates cyclooxygenase 1", body)
    assert _matches("and thereby reduces prostaglandin synthesis", body)


def test_jats_dehyphenates_soft_wrap():
    body = pf.normalize_jats(JATS_SAMPLE)
    assert "cyclooxygenase" in norm(body)
    assert "cyclo oxygenase" not in norm(body)


def test_jats_drops_inline_citation_marker():
    body = pf.normalize_jats(JATS_SAMPLE)
    # If "12" had leaked between "cox 1" and "and", this phrase would not match.
    assert _matches("cox 1 and thereby", body)


def test_jats_flattens_subscripts():
    body = pf.normalize_jats(JATS_SAMPLE)
    assert "h2o2" in norm(body)


def test_jats_keeps_caption_drops_table_cells():
    body = pf.normalize_jats(JATS_SAMPLE)
    assert _matches("Summary of effects", body)   # caption kept
    assert "9999" not in body and "8888" not in body  # raw cells dropped


def test_jats_excludes_bibliography_and_front_abstract():
    body = pf.normalize_jats(JATS_SAMPLE)
    assert "bibliographytoken" not in norm(body)   # <ref-list> excluded
    assert "abstractonlytoken" not in norm(body)   # <front> abstract excluded


def test_jats_neutralizes_undefined_entities_without_error():
    # &alpha; is an undefined entity for ElementTree; _sanitize_xml must save it.
    body = pf.normalize_jats(JATS_SAMPLE)
    assert _matches("tubulin were measured", body)


# ─── normalize_bioc ──────────────────────────────────────────────────────────

def test_bioc_keeps_prose_drops_references():
    body = pf.normalize_bioc(BIOC_SAMPLE)
    assert _matches("Aspirin reduced prostaglandin synthesis", body)
    assert _matches("aspirin and COX-1 inhibition", body)
    assert "biocreftoken" not in norm(body)


# ─── helpers ─────────────────────────────────────────────────────────────────

def test_host_routing():
    assert pf._host_of("https://www.ebi.ac.uk/europepmc/webservices/rest/search") == "www.ebi.ac.uk"
    assert pf._host_of(f"{pf.EUTILS_BASE}/efetch.fcgi") == "eutils.ncbi.nlm.nih.gov"
    assert pf._HOST_INTERVALS[pf.EUROPEPMC_HOST] < pf._HOST_INTERVALS[pf.PUBTATOR_HOST]


def test_cache_content_type_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "CACHE_DIR", tmp_path)
    p = pf._write_cache("999", {"title": "T", "abstract": "x"}, content_type="abstract")
    assert pf._cache_content_type(p) == "abstract"
    p2 = pf._write_cache("999", {"title": "T"}, content_type="full_text", body="full body text here")
    assert pf._cache_content_type(p2) == "full_text"
    assert "## Content" in p2.read_text()


# ─── network-gated smoke tests (opt-in) ──────────────────────────────────────

NETWORK = os.environ.get("DMDB_NETWORK_TESTS") == "1"
net = pytest.mark.skipif(not NETWORK, reason="set DMDB_NETWORK_TESTS=1 to run network tests")


def _a_live_oa_pmid() -> str:
    """Discover a currently-OA PMID via Europe PMC (recent PMIDs churn)."""
    import json
    import urllib.parse
    q = urllib.parse.quote("aspirin AND OPEN_ACCESS:Y AND IN_EPMC:Y")
    url = f"{pf.EUROPEPMC_BASE}/search?query={q}&resultType=core&format=json&pageSize=10"
    data = json.loads(pf._http_get(url, accept="application/json"))
    for r in (data.get("resultList") or {}).get("result", []):
        if r.get("pmid") and r.get("pmcid"):
            return r["pmid"]
    pytest.skip("no live OA PMID found")


@net
def test_probe_open_access_pmid():
    res = pf.probe(_a_live_oa_pmid())
    assert res["pmcid"] and res["fulltext_available"] is True
    # A non-OA article must report unavailable (not an error).
    neg = pf.probe("PMID:23423902")
    assert neg["fulltext_available"] is False and not neg.get("error")


@net
def test_fetch_fulltext_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "CACHE_DIR", tmp_path)
    pmid = _a_live_oa_pmid()
    res = pf.fetch_fulltext_one(pmid, force=True)
    assert res.get("content_type") == "full_text", res
    p = Path(res["path"])
    assert pf._cache_content_type(p) == "full_text"
    # A real sentence from the fetched body must validate as a Layer-4 substring.
    body = p.read_text().split("## Content", 1)[1]
    import re
    sents = [s.strip() for s in re.split(r"(?<=[.])\s+", body) if 40 < len(s.strip()) < 160]
    assert sents and any(_matches(s, body) for s in sents)
