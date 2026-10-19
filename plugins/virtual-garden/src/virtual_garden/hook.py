"""Entry point the Claude Code mod runs after each response.

Reads the Stop hook payload on stdin, applies the turn to the garden once and
prints ``{"systemMessage", "summary", "full", "language"}``; the mod
(``hooks/register.tsx``) draws it above the prompt. Any failure is logged to
the data directory and the script exits quietly, so it never disrupts a
session.

Run by hand with ``--text``, ``--full`` or ``--switch`` it shows or changes
the garden without reading stdin.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cli import add_manual_args, is_manual, log_error, present, print_garden, run_switch, wanted_species
from .config import data_dir, load_settings
from .state import record_turn
from .transcript import last_turn, load_when_flushed

FLUSH_TIMEOUT_S = 3.0


def handle_stop(payload: Dict[str, Any]) -> Dict[str, object]:
    settings = load_settings()
    session = str(payload.get("session_id") or "")
    transcript = payload.get("transcript_path")
    turn = None
    if transcript:
        path = Path(transcript)
        turn = last_turn(load_when_flushed(path, payload.get("last_assistant_message"), FLUSH_TIMEOUT_S))
        session = session or path.stem
    key, metrics = turn if turn else ("", None)
    state, events = record_turn(data_dir(), f"claude:{session}:{key}", metrics, wanted_species(settings))
    return present(state, events, settings, seed=f"{session}:{key}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Virtual Garden for Claude Code")
    add_manual_args(parser)
    args = parser.parse_args(argv)
    settings = load_settings()

    if args.switch:
        return run_switch(args.switch, settings)
    if is_manual(args) or sys.stdin.isatty():
        print_garden(None, [], settings, full=args.full)
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
        out = handle_stop(payload if isinstance(payload, dict) else {})
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        log_error("claude-hook")
    return 0
