"""Bring the history up to date with every Claude Code session.

The band records the turn it just measured, so on its own the day and month
totals would miss sessions in other windows, sessions that started before the
plugin was installed, turns interrupted with Esc (no ``Stop``) and any turn
whose ``Stop`` never reached the band. After each response this module reads
the transcripts that changed since its last run, splits them into turns and
records every turn the history lacks or holds with other token counts.

Only transcripts touched since the start of last month are read, and
``sync-state.json`` remembers each one's size and modification time, so a
response usually re-reads just the sessions that are active. Each run stops
after ``BUDGET_S`` seconds and picks up where it left off on the next one.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from . import history
from .config import claude_config_dir
from .footprint import FootprintModel
from .meter import aggregate
from .pricing import PriceBook
from .transcript import read_entries, session_turns, subagent_transcripts, turn_id

STATE_FILE = "sync-state.json"
STATE_VERSION = 1
# The mod gives the whole script 15 s. A first run over a month of sessions can
# take longer than this budget; what is left over is read after the next response.
BUDGET_S = 6.0


def _since(now: datetime) -> float:
    """Start of last month, as a timestamp."""
    year, month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    return now.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()


def _signature(files: List[Path]) -> List[List[int]]:
    signature = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append([stat.st_size, stat.st_mtime_ns])
    return signature


def _when(prompt: Optional[dict], calls: list) -> Optional[datetime]:
    """When the turn opened, in local time."""
    stamps = [str((prompt or {}).get("timestamp") or "")] + sorted(c.timestamp for c in calls if c.timestamp)
    for stamp in stamps:
        if stamp:
            try:
                return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
            except ValueError:
                continue
    return None


def _load_state(path: Path) -> Dict[str, List[List[int]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or data.get("v") != STATE_VERSION:
        return {}
    files = data.get("files")
    return files if isinstance(files, dict) else {}


def _save_state(path: Path, files: Dict[str, List[List[int]]]) -> None:
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps({"v": STATE_VERSION, "files": files}, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)  # atomic, so two sessions syncing at once never leave a torn file


def sync(
    root: Path,
    prices: PriceBook,
    footprint: FootprintModel,
    profile: str = "central",
    water_scope: str = "full",
    projects: Optional[Path] = None,
    now: Optional[datetime] = None,
    budget_s: float = BUDGET_S,
) -> int:
    """Record the turns the history is missing. Returns how many were recorded."""
    projects = projects or claude_config_dir() / "projects"
    since = _since(now or datetime.now(timezone.utc).astimezone())
    state_path = root / STATE_FILE
    state = _load_state(state_path)
    known = history.latest(root)
    recorded = 0
    deadline = time.monotonic() + budget_s

    # Newest first, so a run that runs out of time has already counted today.
    found = [(_signature([path]), path) for path in projects.glob("*/*.jsonl")]
    transcripts = [path for sig, path in sorted(found, key=lambda f: f[0][0][1] if f[0] else 0, reverse=True)]
    for transcript in transcripts:
        if time.monotonic() >= deadline:
            break
        files = [transcript] + subagent_transcripts(transcript)
        signature = _signature(files)
        key = str(transcript)
        if not signature or state.get(key) == signature:
            continue
        if max(mtime for _, mtime in signature) / 1e9 < since:
            continue
        session = transcript.stem
        for prompt, calls in session_turns(transcript, read_entries(transcript)):
            totals = aggregate(calls, prices, footprint, profile, water_scope)
            turn = turn_id(prompt)
            row = known.get((session, turn))
            if row and row.get("usage") == totals.usage.to_dict():
                continue
            when = _when(prompt, calls)
            if when is None or when.timestamp() < since:
                continue
            history.record(root, session, turn, totals, when)
            recorded += 1
        state[key] = signature

    # Forget transcripts Claude Code has cleaned up.
    state = {k: v for k, v in state.items() if Path(k).exists()}
    root.mkdir(parents=True, exist_ok=True)
    _save_state(state_path, state)
    return recorded
