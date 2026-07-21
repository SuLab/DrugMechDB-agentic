"""
Bulk re-curation campaign framework — a build-only scaffold that NEVER auto-runs curation.

This is the framework for re-curating the whole corpus (every existing (drug, disease)
record gets a fresh AI-curated path). It does three jobs and nothing else:

  1. Enumerate the work list — every record, from kb/paths/_index.yaml.
  2. Track per-record status in a resumable, idempotent status file so an interrupted
     campaign resumes without redoing finished records.
  3. Dispatch work through a pluggable Backend and stamp provenance on each result.

Backends:
  - StubBackend  — deterministic, no API calls. Lets the whole framework (enumerate,
                   resume, status, provenance) be exercised offline — no spend, no real
                   curation — which is how it is tested.
  - BatchBackend — Anthropic Message Batches API (50% cheaper, async bulk). Submits one
                   request per work item, polls until the batch ends, and collects results
                   keyed by custom_id.

**The agentic-loop caveat (why batch is not the whole story).** `/curate` is a MULTI-TURN
loop (search PubMed -> fetch -> draft -> QC -> iterate). The Batches API runs each request
as a SINGLE model turn, so a batch request cannot itself execute the tool loop. The
BatchBackend is therefore for the *batchable* single-turn step; the full interactive loop
runs through a different backend. `build_request` / `parse_result` are injected so the unit
of batchable work is defined by the caller, not hard-coded here.

**Safety:** this module never submits a real batch on import or by default. The CLI defaults
to a dry-run plan; `--stub` exercises the framework offline. Submitting a real batch is an
explicit, deliberate call (`CampaignRunner.run(BatchBackend(...))`), never the default.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import yaml

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "kb" / "paths" / "_index.yaml"
STATUS_FILE = REPO / "_recuration_status.yaml"   # generated, gitignore-able; resumable state (not in kb/paths — never a curation record)
PROMPT_FILES = ["AGENTS.md", "CurationGuide.md"]                  # provenance: what guided curation


# ── work list ─────────────────────────────────────────────────────────────────

@dataclass
class WorkItem:
    id: str
    drug: str | None = None
    disease: str | None = None
    drug_mesh: str | None = None
    disease_mesh: str | None = None
    drugbank: str | None = None


def enumerate_work() -> list[WorkItem]:
    """Every record in the corpus, from the generated index. No prioritization —
    the whole corpus is in scope, in deterministic _id order."""
    doc = yaml.safe_load(INDEX.read_text(encoding="utf-8"))
    entries = doc.values() if isinstance(doc, dict) else doc
    items = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        items.append(WorkItem(
            id=e.get("id") or e.get("_id") or (e.get("file", "").removesuffix(".yaml")),
            drug=e.get("drug"), disease=e.get("disease"),
            drug_mesh=e.get("drug_mesh"), disease_mesh=e.get("disease_mesh"),
            drugbank=e.get("drugbank"),
        ))
    items.sort(key=lambda w: w.id or "")
    return items


# ── provenance ──────────────────────────────────────────────────────────────

def prompt_version() -> str:
    """A stable fingerprint of the curation guidance (AGENTS.md + CurationGuide.md),
    so every curated record records exactly which rules produced it."""
    h = hashlib.sha256()
    for name in PROMPT_FILES:
        p = REPO / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


def make_provenance(model: str, run_id: str, batch_id: str | None = None) -> dict:
    return {
        "model": model,
        "prompt_version": prompt_version(),
        "git_sha": git_sha(),
        "run_id": run_id,
        "batch_id": batch_id,
        "curated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


# ── resumable status store ────────────────────────────────────────────────────

@dataclass
class StatusStore:
    path: Path = STATUS_FILE
    records: dict = field(default_factory=dict)   # id -> {state, batch_id, provenance, error}

    STATES = ("pending", "submitted", "done", "failed")

    @classmethod
    def load(cls, path: Path = STATUS_FILE) -> "StatusStore":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        return cls(path=path, records=(data or {}).get("records", {}))

    def save(self) -> None:
        self.path.write_text(
            yaml.safe_dump({"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                            "records": self.records}, sort_keys=False, allow_unicode=True),
            encoding="utf-8")

    def state(self, item_id: str) -> str:
        return self.records.get(item_id, {}).get("state", "pending")

    def pending(self, items: list[WorkItem]) -> list[WorkItem]:
        """Resumability + idempotency: only items not already done."""
        return [w for w in items if self.state(w.id) != "done"]

    def mark(self, item_id: str, state: str, **extra) -> None:
        assert state in self.STATES, state
        rec = self.records.setdefault(item_id, {})
        rec["state"] = state
        rec.update({k: v for k, v in extra.items() if v is not None})

    def counts(self) -> dict:
        c = {s: 0 for s in self.STATES}
        for rec in self.records.values():
            c[rec.get("state", "pending")] = c.get(rec.get("state", "pending"), 0) + 1
        return c


# ── backends ──────────────────────────────────────────────────────────────────

@dataclass
class ItemResult:
    item_id: str
    ok: bool
    error: str | None = None


class Backend(Protocol):
    name: str
    def run(self, items: list[WorkItem],
            build_request: Callable[[WorkItem], object] | None,
            parse_result: Callable[[str, object], ItemResult] | None) -> dict[str, ItemResult]: ...


class StubBackend:
    """Offline, deterministic — fabricates a result per item so the orchestration
    (enumerate, resume, status, provenance) is testable with no API and no curation."""
    name = "stub"

    def __init__(self, fail_ids: set[str] | None = None):
        self.fail_ids = fail_ids or set()

    def run(self, items, build_request=None, parse_result=None) -> dict[str, ItemResult]:
        out = {}
        for w in items:
            ok = w.id not in self.fail_ids
            out[w.id] = ItemResult(w.id, ok, None if ok else "stub-forced-failure")
        return out


class BatchBackend:
    """Anthropic Message Batches API (50% cheaper, async). Submits one request per item,
    polls until the batch ends, and returns results keyed by custom_id. Requires the caller
    to inject `build_request` (WorkItem -> anthropic Request) and `parse_result`
    (custom_id, batch-result -> ItemResult), because the batchable unit of curation is a
    product decision (see the agentic-loop caveat in the module docstring)."""
    name = "batch"

    def __init__(self, poll_seconds: int = 60):
        import anthropic  # imported lazily so the framework loads without the SDK
        self.client = anthropic.Anthropic()
        self.poll_seconds = poll_seconds

    def run(self, items, build_request, parse_result) -> dict[str, ItemResult]:
        if build_request is None or parse_result is None:
            raise ValueError("BatchBackend requires build_request and parse_result")
        import time
        requests = [build_request(w) for w in items]
        batch = self.client.messages.batches.create(requests=requests)
        while self.client.messages.batches.retrieve(batch.id).processing_status != "ended":
            time.sleep(self.poll_seconds)
        out: dict[str, ItemResult] = {}
        for r in self.client.messages.batches.results(batch.id):   # any order — key by custom_id
            out[r.custom_id] = parse_result(r.custom_id, r)
        return out, batch.id  # type: ignore[return-value]


# ── runner ──────────────────────────────────────────────────────────────────

@dataclass
class CampaignRunner:
    model: str = "claude-opus-4-8"
    status: StatusStore = field(default_factory=StatusStore.load)

    def plan(self) -> tuple[list[WorkItem], list[WorkItem]]:
        """(all_items, pending_items) — dry-run view, submits nothing."""
        allw = enumerate_work()
        return allw, self.status.pending(allw)

    def run(self, backend: Backend, *, build_request=None, parse_result=None,
            limit: int | None = None) -> dict[str, ItemResult]:
        """Dispatch pending items through the backend, stamp provenance, persist status.
        Resumable + idempotent: already-done items are skipped."""
        _, pending = self.plan()
        if limit is not None:
            pending = pending[:limit]
        run_id = uuid.uuid4().hex[:12]
        for w in pending:
            self.status.mark(w.id, "submitted", run_id=run_id)
        self.status.save()

        ran = backend.run(pending, build_request, parse_result)
        results, batch_id = (ran if isinstance(ran, tuple) else (ran, None))

        prov = make_provenance(self.model, run_id, batch_id)
        for w in pending:
            res = results.get(w.id)
            if res is not None and res.ok:
                self.status.mark(w.id, "done", provenance=prov)
            else:
                self.status.mark(w.id, "failed", error=(res.error if res else "no result"))
        self.status.save()
        return results


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="print campaign status and exit")
    ap.add_argument("--stub", action="store_true",
                    help="run pending items through the offline StubBackend (no API, no curation)")
    ap.add_argument("--limit", type=int, default=None, help="cap items processed this run")
    args = ap.parse_args()

    runner = CampaignRunner()
    allw, pending = runner.plan()

    if args.status:
        c = runner.status.counts()
        print(f"Campaign: {len(allw)} records total · {len(pending)} pending")
        print("  status:", ", ".join(f"{k}={v}" for k, v in c.items() if v))
        return 0

    if args.stub:
        results = runner.run(StubBackend(), limit=args.limit)
        ok = sum(1 for r in results.values() if r.ok)
        print(f"[stub] processed {len(results)} · ok {ok} · status file: {STATUS_FILE.name}")
        return 0

    # Default: dry-run plan. Never submits a real batch.
    print(f"DRY RUN — {len(allw)} records, {len(pending)} pending (nothing submitted).")
    print("  --stub    run the framework offline (StubBackend)")
    print("  --status  show progress")
    print("  A real batch run is an explicit CampaignRunner.run(BatchBackend(...)) call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
