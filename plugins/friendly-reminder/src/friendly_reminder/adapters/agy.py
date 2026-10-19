"""Antigravity (agy) adapter for Friendly Reminder.

Reads Antigravity conversation transcripts (JSONL) and computes the turn's
token usage, estimated energy, water consumption and API cost.

Runs as an Antigravity ``Stop`` hook, which records each finished turn in the
shared history without touching the conversation, or directly from the
command line, which prints the reminder for the latest turn.
"""

from __future__ import annotations

import argparse
import json
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

DEFAULT_MODEL = "gemini-3.8-flash"
TRANSCRIPT_GLOB = ".gemini/*/brain/*/.system_generated/logs/transcript.jsonl"
HOOK_NAME = "friendly-reminder"
LAUNCHER = Path(__file__).resolve().parents[3] / "scripts" / "friendly-reminder-agy"

NO_ACTIVITY = {
    "en": "Friendly Reminder: no measured turn found in the transcript.",
    "pt": "Friendly Reminder: nenhum turno medido no transcript.",
}


def find_latest_agy_transcript() -> Optional[Path]:
    """The most recently modified Antigravity transcript, from any installation
    (antigravity-cli, antigravity-ide, the app) and any workspace."""
    matches = list(Path.home().glob(TRANSCRIPT_GLOB))
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def configured_model() -> str:
    """The model picked in the agy CLI settings, e.g. ``Gemini 3.8 Flash (Low)``.

    Transcripts do not record the model, so this is the fallback when the hook
    payload has no ``modelName`` (a manual run).
    """
    try:
        data = json.loads((Path.home() / ".gemini" / "antigravity-cli" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_MODEL
    model = data.get("model") if isinstance(data, dict) else None
    return str(model).strip() if isinstance(model, str) and model.strip() else DEFAULT_MODEL


def conversation_id(transcript_path: Path, payload: Optional[Dict[str, Any]] = None) -> str:
    """The conversation a transcript belongs to.

    Taken from the path (``brain/<id>/.system_generated/logs/transcript.jsonl``)
    so the hook and a manual run record the same turn under the same key.
    """
    logs = transcript_path.parent
    if logs.name == "logs" and logs.parent.name == ".system_generated":
        return logs.parent.parent.name
    payload = payload or {}
    return str(payload.get("conversationId") or payload.get("conversation_id") or transcript_path.stem)


def turn_key(prompt: Optional[Dict[str, Any]]) -> str:
    """The key a turn is recorded under: its opening ``USER_INPUT`` step."""
    prompt = prompt or {}
    if prompt.get("step_index") is not None:
        return str(prompt["step_index"])
    return str(prompt.get("created_at") or "turn")


def _read_entries(path: Path) -> List[Dict[str, Any]]:
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
    except OSError:
        return []
    return entries


def _calls(entries: List[Dict[str, Any]], model_name: str) -> List[ApiCall]:
    calls: List[ApiCall] = []
    for entry in entries:
        if entry.get("type") != "PLANNER_RESPONSE":
            continue
        step_idx = entry.get("step_index", len(calls))
        usage = Usage(
            input=int(entry.get("input_tokens", 0) or 0),
            cache_read=int(entry.get("cache_read_tokens", 0) or 0),
            output=int(entry.get("output_tokens", 0) or 0),
            # Not written by agy today; read in case a later version adds it.
            cache_write_5m=int(entry.get("cache_write_tokens", 0) or 0),
        )
        calls.append(
            ApiCall(
                message_id=f"step_{step_idx}",
                # Transcripts carry no model today; use one if a later version adds it.
                model=str(entry.get("model") or "").strip() or model_name,
                usage=usage,
                timestamp=str(entry.get("created_at") or ""),
            )
        )
    return calls


def parse_agy_transcript(
    path: Path,
    model_name: str = DEFAULT_MODEL,
) -> Tuple[List[ApiCall], Optional[Dict[str, Any]], int]:
    """The API calls of the latest turn that has any, its prompt and its number.

    A turn runs from one ``USER_INPUT`` to the next. Prompts that got no
    response (queued, cancelled) are skipped, so the result is the last turn
    the model actually answered.

    Returns:
        (calls, prompt_entry, turn_number)
    """
    entries = _read_entries(path)
    starts = [i for i, e in enumerate(entries) if e.get("type") == "USER_INPUT"]
    if not starts:
        # Resumed or script-driven session with no explicit USER_INPUT.
        calls = _calls(entries, model_name)
        return calls, None, 1 if calls else 0

    bounds = starts + [len(entries)]
    for n in range(len(starts) - 1, -1, -1):
        calls = _calls(entries[bounds[n] : bounds[n + 1]], model_name)
        if calls:
            return calls, entries[bounds[n]], n + 1
    return [], None, 0


class AgyAdapter:
    """Measures the latest Antigravity turn, records it and renders the reminder."""

    def __init__(self, data_folder: Optional[Path] = None):
        self.data_folder = data_folder or data_dir()

    def build_message(self, payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
        payload = payload or {}
        transcript_str = payload.get("transcriptPath") or payload.get("transcript_path")
        transcript_path = Path(transcript_str) if transcript_str else find_latest_agy_transcript()
        if not transcript_path or not transcript_path.is_file():
            return None

        settings = load_settings()
        prices = PriceBook.load(
            BUNDLED_DATA / "pricing.json",
            self.data_folder and self.data_folder / "pricing.json",
        )
        footprint = FootprintModel.load(
            BUNDLED_DATA / "footprint.json",
            self.data_folder and self.data_folder / "footprint.json",
        )

        model_name = payload.get("modelName") or configured_model()
        calls, prompt, turn_number = parse_agy_transcript(transcript_path, model_name)
        if not calls:
            return None

        turn = aggregate(calls, prices, footprint, settings.footprint_profile, settings.water_scope)

        session = conversation_id(transcript_path, payload)
        key = turn_key(prompt)
        today = month = None
        months = []
        if self.data_folder:
            history.record(self.data_folder, session, key, turn)
            today, month = history.summary(self.data_folder)
            months = history.monthly(self.data_folder)

        # Billing detection for agy is not implemented; "unknown" makes the
        # render layer skip quota lines instead of guessing a plan.
        billing = Billing(mode="unknown")
        language = settings.language if settings.language != "auto" else detect_language()

        return render(
            turn,
            turn_number,
            settings,
            language,
            billing,
            today=today,
            month=month,
            months=months,
            seed=f"{session}:{key}",
        )


def build_agy_message(payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
    return AgyAdapter().build_message(payload)


def install_hook(hooks_file: Optional[Path] = None) -> Path:
    """Register the ``Stop`` hook in agy's global hooks file, by absolute path.

    Other hooks in the file are kept; an earlier entry of this one is replaced.
    """
    hooks_file = hooks_file or Path.home() / ".gemini" / "config" / "hooks.json"
    try:
        data = json.loads(hooks_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data[HOOK_NAME] = {"Stop": [{"type": "command", "command": str(LAUNCHER), "timeout": 10}]}
    hooks_file.parent.mkdir(parents=True, exist_ok=True)
    hooks_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return hooks_file


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
    parser.add_argument("--text", "-t", action="store_true", help="Print the reminder even when stdin is a pipe")
    parser.add_argument("--transcript", "-p", type=str, help="Explicit path to transcript.jsonl")
    parser.add_argument(
        "--install-hook", action="store_true", help="Register the Stop hook in ~/.gemini/config/hooks.json"
    )
    args = parser.parse_args(argv)

    if args.install_hook:
        sys.stdout.write(f"Friendly Reminder: Stop hook registered in {install_hook()}\n")
        return 0

    payload: Dict[str, Any] = {}
    is_hook = False
    # A manual run (--text) never reads stdin: an agent's shell can hand it a
    # pipe that is never closed, and reading it would hang.
    if not args.text and not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                payload = json.loads(raw)
                is_hook = isinstance(payload, dict)
        except (OSError, ValueError):  # unreadable stdin or not JSON
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    if args.transcript:
        payload["transcriptPath"] = args.transcript

    try:
        message = build_agy_message(payload)
    except Exception:  # noqa: BLE001 - a hook must never break the session
        _log_error()
        message = None

    if is_hook:
        # Stop hook: the turn is already recorded; let the agent stop. Anything
        # other than "continue" allows it, and nothing reaches the model.
        sys.stdout.write(json.dumps({"decision": "allow"}) + "\n")
    elif message:
        sys.stdout.write(message + "\n")
    else:
        settings = load_settings()
        language = settings.language if settings.language != "auto" else detect_language()
        sys.stdout.write(NO_ACTIVITY.get(language, NO_ACTIVITY["en"]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
