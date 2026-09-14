"""Corpus-level term audit: resolve every node id, compare every node name.

Two independent findings per node, deliberately kept separate because they have
different causes and different fixes:

    existence    the CURIE does not resolve (ABSENT) or has aged out (OBSOLETE)
    name         the CURIE resolves, but the record's `name` is not the
                 ontology's canonical label

A name mismatch is the weaker signal of the two — ontologies carry synonyms the
record may legitimately prefer — so it is reported separately and never
conflated with a missing identifier.

Resolution is deduplicated across the corpus: 33,009 node instances collapse to
about 5,100 unique CURIEs, so the network cost is ~6x smaller than it looks.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from .resolvers import Registry, name_similarity, names_match, normalize_label
from .types import TermResult, TermStatus


@dataclass(frozen=True)
class NodeRef:
    """One node occurrence in one file."""
    file: str
    index: int
    curie: str
    name: str | None
    label: str | None


@dataclass
class Finding:
    kind: str                 # "existence" | "name"
    node: NodeRef
    result: TermResult
    detail: str
    similarity: float | None = None
    """Token overlap between the record name and the canonical label, for
    `name` findings. Lower = more suspicious. Ranking only, never a verdict."""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "similarity": self.similarity,
            "file": self.node.file,
            "node_index": self.node.index,
            "curie": self.node.curie,
            "record_name": self.node.name,
            "biolink_label": self.node.label,
            "status": self.result.status.value,
            "canonical_label": self.result.label,
            "source": self.result.source,
            "detail": self.detail,
        }


@dataclass
class AuditReport:
    files_checked: int = 0
    nodes_checked: int = 0
    unique_curies: int = 0
    status_counts: Counter = field(default_factory=Counter)
    prefix_status: dict[str, Counter] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    resolutions: dict[str, TermResult] = field(default_factory=dict)

    @property
    def existence_failures(self) -> list[Finding]:
        return [f for f in self.findings if f.kind == "existence"]

    @property
    def name_mismatches(self) -> list[Finding]:
        return [f for f in self.findings if f.kind == "name"]

    def to_dict(self) -> dict:
        return {
            "files_checked": self.files_checked,
            "nodes_checked": self.nodes_checked,
            "unique_curies": self.unique_curies,
            "status_counts": dict(self.status_counts),
            "prefix_status": {p: dict(c) for p, c in sorted(self.prefix_status.items())},
            "existence_failure_count": len(self.existence_failures),
            "name_mismatch_count": len(self.name_mismatches),
            "findings": [f.to_dict() for f in self.findings],
        }


def iter_nodes(files: Iterable[Path]) -> Iterable[NodeRef]:
    for path in files:
        doc = yaml.safe_load(path.read_text())
        if not isinstance(doc, dict):
            continue
        for i, node in enumerate(doc.get("nodes") or []):
            if not isinstance(node, dict):
                continue
            curie = node.get("id")
            if not isinstance(curie, str):
                continue
            yield NodeRef(str(path), i, curie, node.get("name"), node.get("label"))


def audit(files: list[Path], registry: Registry,
          *, check_names: bool = True,
          progress: callable | None = None) -> AuditReport:
    """Resolve every node id across `files` and collect findings."""
    report = AuditReport(files_checked=len(files))
    nodes = list(iter_nodes(files))
    report.nodes_checked = len(nodes)

    unique = sorted({n.curie for n in nodes})
    report.unique_curies = len(unique)

    for i, curie in enumerate(unique, 1):
        report.resolutions[curie] = registry.resolve(curie)
        if progress and (i % 100 == 0 or i == len(unique)):
            progress(i, len(unique))

    seen_existence: set[str] = set()
    seen_name: set[tuple[str, str]] = set()

    for node in nodes:
        result = report.resolutions[node.curie]
        prefix = node.curie.split(":", 1)[0]
        report.status_counts[result.status.value] += 1
        report.prefix_status.setdefault(prefix, Counter())[result.status.value] += 1

        if result.status in (TermStatus.ABSENT, TermStatus.OBSOLETE):
            # One finding per distinct CURIE, not per occurrence — otherwise a
            # single bad id used in 40 records reads as 40 problems.
            if node.curie not in seen_existence:
                seen_existence.add(node.curie)
                detail = (result.detail or
                          ("identifier does not resolve in its source ontology"
                           if result.status is TermStatus.ABSENT
                           else "identifier is deprecated upstream"))
                report.findings.append(Finding("existence", node, result, detail))
            continue

        if not check_names or result.status is not TermStatus.EXISTS:
            continue
        if not result.label or not node.name:
            continue
        if not names_match(node.name, result):
            key = (node.curie, normalize_label(node.name))
            if key not in seen_name:
                seen_name.add(key)
                report.findings.append(Finding(
                    "name", node, result,
                    f"record name {node.name!r} is not the canonical label "
                    f"{result.label!r} nor any synonym the authority returned",
                    similarity=name_similarity(node.name, result.label)))

    # Existence failures first, then name findings least-plausible-first.
    report.findings.sort(key=lambda f: (f.kind != "existence",
                                        f.similarity if f.similarity is not None else 0.0))
    return report
