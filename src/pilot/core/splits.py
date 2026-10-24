"""Persistent run history and personal bests (JSON under %APPDATA%/poe2-pilot/runs)."""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)
_PB_FILE = "pb.json"


def default_runs_dir() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / "poe2-pilot" / "runs"


@dataclass
class ZoneSegment:
    """Per-zone statistics of one run (game seconds, loading screens excluded)."""
    area_id: str
    area_name: str = ""
    first_s: float = 0.0          # game time of the first entry
    seconds: float = 0.0          # game time spent, summed over visits
    visits: int = 0
    loading_s: float = 0.0        # loading-screen seconds (already excluded from `seconds`)
    deaths: int = 0
    is_town: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunRecord:
    """One finished or abandoned run. `splits` maps split id -> cumulative game seconds."""
    route_id: str
    status: str                      # "finished" | "abandoned"
    started_at: str                  # ISO timestamp of the log event that started the run
    total_s: float
    splits: dict[str, float] = field(default_factory=dict)
    deaths: int = 0
    segments: list[dict] = field(default_factory=list)   # ZoneSegment dicts; absent in old files

    def zone_segments(self) -> list[ZoneSegment]:
        return [ZoneSegment(**d) for d in self.segments]


class SplitStore:
    """Saves runs as individual JSON files and keeps best times in `pb.json`.

    PBs (per split id, and total) are taken from finished runs only.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_runs_dir()
        self._lock = threading.Lock()
        self._pb: dict = self._load_pb()

    # ---- queries ----
    def pb_split(self, route_id: str, split_id: str) -> float | None:
        with self._lock:
            return self._pb.get(route_id, {}).get("splits", {}).get(split_id)

    def pb_total(self, route_id: str) -> float | None:
        with self._lock:
            return self._pb.get(route_id, {}).get("total")

    def delta(self, route_id: str, split_id: str, t: float) -> float | None:
        """t minus PB at this split (negative = ahead); None when there is no PB."""
        pb = self.pb_split(route_id, split_id)
        return None if pb is None else t - pb

    def list_runs(self, route_id: str | None = None) -> list[RunRecord]:
        out: list[RunRecord] = []
        for p in sorted(self.root.glob("run_*.json")):
            try:
                rec = RunRecord(**json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                continue
            if route_id is None or rec.route_id == route_id:
                out.append(rec)
        return out

    # ---- writes ----
    def save_run(self, rec: RunRecord) -> Path:
        """Persist a run; a finished run also updates PBs."""
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            stamp = "".join(c for c in rec.started_at if c.isdigit())[:14] or "0"
            base = f"run_{stamp}_{rec.status}"
            path = self.root / f"{base}.json"
            n = 1
            while path.exists():
                n += 1
                path = self.root / f"{base}_{n}.json"
            self._write(path, asdict(rec))
            if rec.status == "finished":
                self._update_pb(rec)
            return path

    def _update_pb(self, rec: RunRecord) -> None:
        entry = self._pb.setdefault(rec.route_id, {"total": None, "splits": {}})
        if entry.get("total") is None or rec.total_s < entry["total"]:
            entry["total"] = rec.total_s
        best = entry.setdefault("splits", {})
        for sid, t in rec.splits.items():
            if sid not in best or t < best[sid]:
                best[sid] = t
        self._write(self.root / _PB_FILE, self._pb)

    def _load_pb(self) -> dict:
        try:
            data = json.loads((self.root / _PB_FILE).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write(path: Path, data: object) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
