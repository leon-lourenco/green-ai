"""Antigravity (agy) adapter for Friendly Reminder.

Reads Antigravity conversation transcripts (JSONL) and computes the turn's
token usage, estimated energy, water consumption and API cost.

Can be run as an Antigravity Lifecycle Hook (e.g. PostInvocation / PreInvocation)
or invoked directly via CLI (python3 -m friendly_reminder.adapters.agy).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import __version__, history
from ..config import BUNDLED_DATA, Billing, data_dir, detect_language, load_settings
from ..footprint import FootprintModel
from ..meter import aggregate
from ..models import ApiCall, Usage
from ..pricing import PriceBook
from ..render import render


def find_latest_agy_transcript() -> Optional[Path]:
    """Auto-detect the most recently modified Antigravity transcript.

    Searches under ``~/.gemini/`` for any installation variant
    (antigravity-cli, antigravity-ide, bare antigravity, …).
    """
    matches = list(Path.home().glob(".gemini/*/brain/*/.system_generated/logs/transcript.jsonl"))
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def parse_agy_transcript(
    path: Path,
    model_name: str = "gemini-3.8-flash",
) -> Tuple[List[ApiCall], Optional[Dict[str, Any]], int]:
    """Parse an Antigravity transcript and extract the latest turn's API calls.

    Token counts come directly from ``PLANNER_RESPONSE`` entries (``input_tokens``,
    ``cache_read_tokens``, ``output_tokens``).  The model name is read from the
    ``model`` field of each entry when present; ``model_name`` is used only as a
    fallback for transcripts that do not carry that field.

    Returns:
        (calls, prompt_entry, turn_count)
    """
    entries: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    entries.append(obj)
    except FileNotFoundError:
        return [], None, 0

    user_turn_indexes = [i for i, e in enumerate(entries) if e.get("type") == "USER_INPUT"]
    turn_count = len(user_turn_indexes)

    if not user_turn_indexes:
        # Resumed or script-driven session with no explicit USER_INPUT
        start_idx = 0
        prompt = None
    else:
        start_idx = user_turn_indexes[-1]
        prompt = entries[start_idx]

    calls: List[ApiCall] = []
    for entry in entries[start_idx:]:
        if entry.get("type") != "PLANNER_RESPONSE":
            continue
        step_idx = entry.get("step_index", len(calls))
        inp = int(entry.get("input_tokens", 0) or 0)
        cache_read = int(entry.get("cache_read_tokens", 0) or 0)
        out = int(entry.get("output_tokens", 0) or 0)
        # cache_write_tokens is not currently exposed by agy transcripts; kept
        # here for forward-compatibility in case it is added in a future version.
        cache_write = int(entry.get("cache_write_tokens", 0) or 0)
        created_at = str(entry.get("created_at") or "")
        # Prefer the model name embedded in the transcript entry over the
        # payload/default, so the right pricing row is used when the user
        # switches models mid-session.
        entry_model = str(entry.get("model") or "").strip() or model_name

        usage = Usage(
            input=inp,
            cache_read=cache_read,
            output=out,
            cache_write_5m=cache_write,
        )
        calls.append(
            ApiCall(
                message_id=f"step_{step_idx}",
                model=entry_model,
                usage=usage,
                timestamp=created_at,
            )
        )

    return calls, prompt, turn_count


class AgyAdapter:
    """Adapter bridging Antigravity transcript and hook execution with Friendly Reminder.

    Implements the :class:`~friendly_reminder.adapters.base.BaseAdapter` protocol.
    """

    def __init__(self, data_folder: Optional[Path] = None):
        self.data_folder = data_folder or data_dir()

    # ------------------------------------------------------------------
    # BaseAdapter protocol
    # ------------------------------------------------------------------

    def session_id(self, payload: Dict[str, Any]) -> str:
        """Stable identifier for the conversation, derived from the transcript path."""
        transcript_str = payload.get("transcriptPath") or payload.get("transcript_path")
        if transcript_str:
            return Path(transcript_str).parent.parent.name
        return str(payload.get("conversationId") or payload.get("conversation_id") or "unknown")

    def turn_key(self, payload: Dict[str, Any]) -> str:
        """Stable identifier for the current turn within the session."""
        return str(payload.get("stepIndex") or payload.get("step_index") or payload.get("created_at") or "turn")

    # ------------------------------------------------------------------

    def build_message(self, payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
        payload = payload or {}
        transcript_str = payload.get("transcriptPath") or payload.get("transcript_path")
        if transcript_str:
            transcript_path = Path(transcript_str)
        else:
            transcript_path = find_latest_agy_transcript()

        if not transcript_path or not transcript_path.is_file():
            return None

        model_name = payload.get("modelName") or "gemini-3.8-flash"
        conversation_id = (
            payload.get("conversationId")
            or payload.get("conversation_id")
            or transcript_path.parent.parent.name
        )

        settings = load_settings()
        prices = PriceBook.load(
            BUNDLED_DATA / "pricing.json",
            self.data_folder and self.data_folder / "pricing.json",
        )
        footprint = FootprintModel.load(
            BUNDLED_DATA / "footprint.json",
            self.data_folder and self.data_folder / "footprint.json",
        )

        calls, prompt, turn_count = parse_agy_transcript(transcript_path, model_name)
        if not calls:
            return None

        turn = aggregate(calls, prices, footprint, settings.footprint_profile, settings.water_scope)

        turn_key = str((prompt or {}).get("step_index") or (prompt or {}).get("created_at") or "turn")
        today = month = None
        months = []
        if self.data_folder:
            history.record(self.data_folder, str(conversation_id), turn_key, turn)
            today, month = history.summary(self.data_folder)
            months = history.monthly(self.data_folder)

        # Billing detection for agy is not yet implemented; use "unknown" so the
        # render layer skips quota display rather than showing incorrect Pro data.
        billing = Billing(mode="unknown")
        language = settings.language if settings.language != "auto" else detect_language()

        return render(
            turn,
            turn_count,
            settings,
            language,
            billing,
            today=today,
            month=month,
            months=months,
            seed=f"{conversation_id}:{turn_key}",
        )


def build_agy_message(payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
    adapter = AgyAdapter()
    return adapter.build_message(payload)


def _log_error() -> None:
    folder = data_dir()
    if not folder:
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "error.log").open("a", encoding="utf-8") as handle:
            handle.write(f"--- {datetime.now().isoformat()} agy-adapter v{__version__}\n{traceback.format_exc()}\n")
    except OSError:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Friendly Reminder adapter for Antigravity (agy)")
    parser.add_argument("--text", "-t", action="store_true", help="Always print plain text output")
    parser.add_argument("--transcript", "-p", type=str, help="Explicit path to transcript.jsonl")
    args = parser.parse_args(argv)

    payload: Dict[str, Any] = {}
    is_stdin_pipe = not sys.stdin.isatty()

    if is_stdin_pipe:
        try:
            raw = sys.stdin.read().strip()
            if raw:
                payload = json.loads(raw)
        except Exception:
            pass

    if args.transcript:
        payload["transcriptPath"] = args.transcript

    try:
        message = build_agy_message(payload)
        if not message:
            if not is_stdin_pipe or args.text:
                sys.stdout.write("Friendly Reminder: No turn activity found in transcript.\n")
            return 0

        # If invoked in an Antigravity hook context and not explicitly requesting plain text
        if is_stdin_pipe and not args.text:
            hook_output = {
                "injectSteps": [
                    {
                        "ephemeralMessage": message,
                    }
                ]
            }
            sys.stdout.write(json.dumps(hook_output, ensure_ascii=False) + "\n")
        else:
            sys.stdout.write(message + "\n")
    except Exception:
        _log_error()

    return 0


if __name__ == "__main__":
    sys.exit(main())
