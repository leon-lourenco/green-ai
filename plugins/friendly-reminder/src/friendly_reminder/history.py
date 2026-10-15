"""Append-only history of measured turns, one file per month.

One JSON line per turn in ``<data dir>/history/YYYY-MM.jsonl``. A turn can be
recorded more than once (a Stop hook that makes Claude continue fires Stop
again for the same turn), so readers keep the last record per
``(session, turn)``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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


def _rows(path: Path) -> Dict[Tuple[Any, Any], Dict[str, Any]]:
    latest: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return latest
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            latest[(row.get("session"), row.get("turn"))] = row
    return latest


def _add(totals: Totals, row: Dict[str, Any]) -> None:
    totals.usage = totals.usage + Usage.from_dict(row.get("usage") or {})
    totals.cost_usd += float(row.get("cost_usd") or 0.0)
    totals.footprint = totals.footprint + Footprint(float(row.get("wh") or 0.0), float(row.get("water_ml") or 0.0))
    totals.turns += 1


def summary(root: Path, when: Optional[datetime] = None) -> Tuple[Totals, Totals]:
    """Totals for (today, this month), in local time."""
    when = when or datetime.now().astimezone()
    today_prefix = f"{when:%Y-%m-%d}"
    day, month = Totals(), Totals()
    for row in _rows(_month_file(root, when)).values():
        _add(month, row)
        if str(row.get("ts", "")).startswith(today_prefix):
            _add(day, row)
    return day, month
