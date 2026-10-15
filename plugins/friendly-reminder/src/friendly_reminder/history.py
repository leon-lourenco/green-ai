"""Append-only history of measured turns, one file per month.

One JSON line per turn in ``<data dir>/history/YYYY-MM.jsonl``. A turn can be
recorded more than once (a Stop hook that makes Claude continue fires Stop
again for the same turn, and ``sync`` records turns the band missed), so
readers keep the last record per ``(session, turn)``, across months. A row
belongs to the month and day of its ``ts``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import Footprint, Totals, Usage

SCHEMA_VERSION = 1


def _month_file(root: Path, when: datetime) -> Path:
    return root / "history" / f"{when:%Y-%m}.jsonl"


def record(root: Path, session_id: str, turn_id: str, totals: Totals, when: Optional[datetime] = None) -> None:
    when = when or datetime.now().astimezone()
    path = _month_file(root, when)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "v": SCHEMA_VERSION,
        "ts": when.isoformat(timespec="seconds"),
        "session": session_id,
        "turn": turn_id,
        "usage": totals.usage.to_dict(),
        "cost_usd": round(totals.cost_usd, 6),
        "wh": round(totals.footprint.wh, 4),
        "water_ml": round(totals.footprint.water_ml, 4),
        "models": sorted(totals.models),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, separators=(",", ":")) + "\n")


def latest(root: Path) -> Dict[Tuple[Any, Any], Dict[str, Any]]:
    """The last record of every turn, across all months."""
    rows: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    for path in sorted((root / "history").glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows[(row.get("session"), row.get("turn"))] = row
    return rows


def _add(totals: Totals, row: Dict[str, Any]) -> None:
    totals.usage = totals.usage + Usage.from_dict(row.get("usage") or {})
    totals.cost_usd += float(row.get("cost_usd") or 0.0)
    totals.footprint = totals.footprint + Footprint(float(row.get("wh") or 0.0), float(row.get("water_ml") or 0.0))
    totals.turns += 1


def summary(root: Path, when: Optional[datetime] = None) -> Tuple[Totals, Totals]:
    """Totals for (today, this month), in local time."""
    when = when or datetime.now().astimezone()
    day, month = Totals(), Totals()
    for row in latest(root).values():
        ts = str(row.get("ts", ""))
        if ts.startswith(f"{when:%Y-%m}"):
            _add(month, row)
            if ts.startswith(f"{when:%Y-%m-%d}"):
                _add(day, row)
    return day, month


def monthly(root: Path, limit: int = 6) -> List[Tuple[str, Totals]]:
    """Totals per month (``YYYY-MM``), newest first."""
    months: Dict[str, Totals] = {}
    for row in latest(root).values():
        key = str(row.get("ts", ""))[:7]
        if len(key) == 7:
            _add(months.setdefault(key, Totals()), row)
    return sorted(months.items(), reverse=True)[:limit]
