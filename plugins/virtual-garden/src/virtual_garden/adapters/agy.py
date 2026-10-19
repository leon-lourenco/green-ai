"""Antigravity (agy) adapter for Virtual Garden.

Runs as an Antigravity ``Stop`` hook, which grows the garden with each
finished turn without touching the conversation, or from the command line,
which applies the latest turn (once) and prints the garden.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..cli import add_manual_args, log_error, print_garden, run_switch, wanted_species
from ..config import data_dir, load_settings
from ..models import Event, GardenState, TurnMetrics
from ..state import record_turn

TRANSCRIPT_GLOB = ".gemini/*/brain/*/.system_generated/logs/transcript.jsonl"
HOOK_NAME = "virtual-garden"
LAUNCHER = Path(__file__).resolve().parents[3] / "scripts" / "virtual-garden-agy"


def find_latest_agy_transcript() -> Optional[Path]:
    """The most recently modified Antigravity transcript, from any installation and workspace."""
    matches = list(Path.home().glob(TRANSCRIPT_GLOB))
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def conversation_id(transcript_path: Path, payload: Optional[Dict[str, Any]] = None) -> str:
    """The conversation folder's id (``brain/<id>/.system_generated/logs/transcript.jsonl``),
    so the hook and a manual run record a turn under the same key."""
    logs = transcript_path.parent
    if logs.name == "logs" and logs.parent.name == ".system_generated":
        return logs.parent.parent.name
    payload = payload or {}
    return str(payload.get("conversationId") or payload.get("conversation_id") or transcript_path.stem)


def _read_entries(path: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    entries.append(obj)
    except OSError:
        pass
    return entries


def parse_agy_turn(path: Path) -> Optional[Tuple[str, TurnMetrics]]:
    """The last turn the model answered: its key (the prompt's step) and metrics.

    A turn runs from one ``USER_INPUT`` to the next; prompts that got no
    ``PLANNER_RESPONSE`` (queued, cancelled) are skipped. agy writes no
    compaction marker, so soil renews only with a new conversation.
    """
    entries = _read_entries(path)
    starts = [i for i, e in enumerate(entries) if e.get("type") == "USER_INPUT"] or [0]
    bounds = starts + [len(entries)]
    answered = []
    for n in range(len(starts)):
        steps = [e for e in entries[bounds[n] : bounds[n + 1]] if e.get("type") == "PLANNER_RESPONSE"]
        if steps:
            answered.append((entries[bounds[n]], steps))
    if not answered:
        return None
    prompt, steps = answered[-1]
    metrics = TurnMetrics(fresh_session=len(answered) == 1, timestamp=str(prompt.get("created_at") or ""))
    for step in steps:
        metrics.input_tokens += int(step.get("input_tokens") or 0)
        metrics.cache_read_tokens += int(step.get("cache_read_tokens") or 0)
        metrics.output_tokens += int(step.get("output_tokens") or 0)
    last = steps[-1]
    metrics.context_tokens = int(last.get("input_tokens") or 0) + int(last.get("cache_read_tokens") or 0)
    key = prompt.get("step_index")
    return str(key if key is not None else prompt.get("created_at") or "turn"), metrics


def record_agy_turn(payload: Optional[Dict[str, Any]] = None) -> Tuple[Optional[GardenState], List[Event]]:
    payload = payload or {}
    transcript = payload.get("transcriptPath") or payload.get("transcript_path")
    path = Path(transcript) if transcript else find_latest_agy_transcript()
    if not path or not path.is_file():
        return None, []
    turn = parse_agy_turn(path)
    if not turn:
        return None, []
    key, metrics = turn
    species = wanted_species(load_settings())
    return record_turn(data_dir(), f"agy:{conversation_id(path, payload)}:{key}", metrics, species)


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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Virtual Garden for Antigravity (agy)")
    add_manual_args(parser)
    parser.add_argument("--transcript", "-p", type=str, help="Explicit path to transcript.jsonl")
    parser.add_argument(
        "--install-hook", action="store_true", help="Register the Stop hook in ~/.gemini/config/hooks.json"
    )
    args = parser.parse_args(argv)
    settings = load_settings()

    if args.install_hook:
        sys.stdout.write(f"Virtual Garden: Stop hook registered in {install_hook()}\n")
        return 0
    if args.switch:
        return run_switch(args.switch, settings)

    payload: Dict[str, Any] = {}
    # A manual run never reads stdin: an agent's shell can hand it a pipe
    # that is never closed, and reading it would hang.
    is_hook = not (args.text or args.full) and not sys.stdin.isatty()
    if is_hook:
        try:
            raw = json.loads(sys.stdin.read() or "{}")
            payload = raw if isinstance(raw, dict) else {}
        except ValueError:
            payload = {}
    if args.transcript:
        payload["transcriptPath"] = args.transcript

    try:
        state, events = record_agy_turn(payload)
    except Exception:  # noqa: BLE001 - a hook must never break the session
        log_error("agy-adapter")
        state, events = None, []

    if is_hook:
        # Antigravity hooks cannot show text; let the agent stop as usual.
        sys.stdout.write(json.dumps({"decision": "allow"}) + "\n")
    else:
        print_garden(state, events, settings, full=args.full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
