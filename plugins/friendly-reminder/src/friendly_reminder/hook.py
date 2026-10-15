"""Entry point the mod runs after each response.

Reads the Stop hook payload on stdin and prints
``{"systemMessage": ..., "language": ...}``; the mod (``hooks/register.tsx``)
draws the message above the prompt. Any failure is logged to the plugin data
directory and the script exits quietly, so it never disrupts a session.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__, history, sync
from .config import BUNDLED_DATA, claude_state_file, data_dir, detect_billing, detect_language, load_settings
from .footprint import FootprintModel
from .meter import aggregate
from .pricing import PriceBook
from .quota import read_quota
from .render import render
from .transcript import load_when_flushed, turn_calls, turn_id, turn_start_indexes

FLUSH_TIMEOUT_S = 3.0


def resolved_language() -> str:
    settings = load_settings()
    return settings.language if settings.language != "auto" else detect_language()


def build_message(payload: Dict[str, Any]) -> Optional[str]:
    transcript = payload.get("transcript_path")
    if not transcript:
        return None
    path = Path(transcript)
    settings = load_settings()  # format "off" still records history, it just shows nothing

    data = data_dir()  # history and optional pricing/footprint overrides
    prices = PriceBook.load(BUNDLED_DATA / "pricing.json", data and data / "pricing.json")
    footprint = FootprintModel.load(BUNDLED_DATA / "footprint.json", data and data / "footprint.json")
    billing = detect_billing()
    language = resolved_language()

    entries, flushed = load_when_flushed(path, payload.get("last_assistant_message"), FLUSH_TIMEOUT_S)
    calls, prompt = turn_calls(path, entries)
    if not calls:
        return None
    turn = aggregate(calls, prices, footprint, settings.footprint_profile, settings.water_scope)

    session_id = str(payload.get("session_id") or path.stem)
    turn_key = turn_id(prompt)
    today = month = None
    months = []
    if data:
        history.record(data, session_id, turn_key, turn)
        try:
            # Other sessions, and turns this band never saw, count in the totals too.
            sync.sync(data, prices, footprint, settings.footprint_profile, settings.water_scope)
        except Exception:  # noqa: BLE001 - the turn's own numbers still show
            _log_error()
        today, month = history.summary(data)
        months = history.monthly(data)

    quota = read_quota(claude_state_file(), billing.plan) if billing.is_subscription else None
    return render(
        turn, len(turn_start_indexes(entries)), settings, language, billing,
        quota=quota, today=today, month=month, months=months, flushed=flushed, seed=f"{session_id}:{turn_key}",
    )


def _log_error() -> None:
    folder = data_dir()
    if not folder:
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "error.log").open("a", encoding="utf-8") as handle:
            handle.write(f"--- {datetime.now().isoformat()} v{__version__}\n{traceback.format_exc()}\n")
    except OSError:
        pass


def main() -> int:
    try:
        message = build_message(json.loads(sys.stdin.read() or "{}"))
        if message:
            sys.stdout.write(json.dumps({"systemMessage": message, "language": resolved_language()}, ensure_ascii=False))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        _log_error()
    return 0
