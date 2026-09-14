"""On-disk cache of term resolutions.

Committed to the repo so that CI, a fresh clone, and a reviewer re-running an
audit all reproduce the same numbers without touching the network. This is the
same pattern Dismech uses for its materialized enum caches.

Layout: one JSON file per CURIE prefix under `cache/terms/`, sorted by key.
Per-prefix files keep git diffs scoped — re-running MeSH doesn't churn GO.

Only EXISTS and ABSENT are cached; both are durable facts about an ontology
release. UNRESOLVED is never cached — it describes our connectivity, not the
data, and caching it would make a transient outage permanent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .types import TermResult, TermStatus

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_CACHE_DIR = REPO / "cache" / "terms"

_SAFE_PREFIX = re.compile(r"^[A-Za-z0-9_.-]+$")


def prefix_of(curie: str) -> str:
    """The prefix of a CURIE, or "_none" when it has no colon."""
    if not isinstance(curie, str) or ":" not in curie:
        return "_none"
    return curie.split(":", 1)[0]


class TermCache:
    """Prefix-sharded, write-through JSON cache keyed by CURIE."""

    def __init__(self, cache_dir: Path | str | None = None):
        self.dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self._shards: dict[str, dict[str, dict]] = {}
        self._dirty: set[str] = set()

    # ── shard io ────────────────────────────────────────────────────────────
    def _shard_path(self, prefix: str) -> Path:
        if not _SAFE_PREFIX.match(prefix):
            prefix = "_other"
        return self.dir / f"{prefix}.json"

    def _shard(self, prefix: str) -> dict[str, dict]:
        if prefix in self._shards:
            return self._shards[prefix]
        path = self._shard_path(prefix)
        data: dict[str, dict] = {}
        if path.exists():
            # A corrupt shard is recoverable (we just re-resolve), but silently
            # discarding it would hide a real problem — so say so and keep going.
            try:
                loaded = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                raise ValueError(f"term cache shard {path} is not valid JSON: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ValueError(f"term cache shard {path} must contain a JSON object")
            data = loaded
        self._shards[prefix] = data
        return data

    # ── api ─────────────────────────────────────────────────────────────────
    def get(self, curie: str) -> TermResult | None:
        entry = self._shard(prefix_of(curie)).get(curie)
        if entry is None:
            return None
        return TermResult.from_dict({**entry, "curie": curie})

    def put(self, result: TermResult) -> None:
        if result.status in (TermStatus.UNRESOLVED, TermStatus.SKIPPED):
            return  # transient / policy, not a fact about the ontology
        prefix = prefix_of(result.curie)
        entry = {k: v for k, v in result.to_dict().items()
                 if k != "curie" and v is not None}
        self._shard(prefix)[result.curie] = entry
        self._dirty.add(prefix)

    def flush(self) -> list[Path]:
        """Write dirty shards. Returns the paths written."""
        written = []
        for prefix in sorted(self._dirty):
            path = self._shard_path(prefix)
            path.parent.mkdir(parents=True, exist_ok=True)
            shard = self._shards[prefix]
            path.write_text(json.dumps(shard, indent=2, sort_keys=True) + "\n")
            written.append(path)
        self._dirty.clear()
        return written

    def __len__(self) -> int:
        total = 0
        if self.dir.exists():
            for path in self.dir.glob("*.json"):
                total += len(self._shard(path.stem))
        return total
