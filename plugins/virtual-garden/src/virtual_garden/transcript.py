"""Read Claude Code session transcripts (JSONL) and measure the last answered turn.

Transcript layout notes (Claude Code 2.1.x), shared with Friendly Reminder:

* One JSON object per line. ``type`` is ``user``, ``assistant``, ``system`` or
  one of many bookkeeping types we ignore.
* A single API response is written as several ``assistant`` lines that repeat
  the same ``message.id`` and ``message.usage``, so calls are de-duplicated
  by message id.
* ``/compact`` and auto-compaction write a ``system`` line with subtype
  ``compact_boundary`` and ``compactMetadata.trigger`` (``manual``/``auto``).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import TurnMetrics

Entry = Dict[str, Any]

FINAL_STOP_REASONS = {"end_turn", "stop_sequence", "max_tokens", "refusal"}
SYNTHETIC_MODELS = {"<synthetic>"}


def read_entries(path: Path) -> List[Entry]:
    """Parse a JSONL file, skipping blank or partially written lines."""
    entries: List[Entry] = []
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
        pass
    return entries


def is_turn_start(entry: Entry) -> bool:
    """True for the user line that opens a turn; false for tool results and meta lines."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    if entry.get("isCompactSummary"):
        return False
    if entry.get("turnOrigin") or entry.get("origin"):
        return True
    if "turnPosition" in entry or "promptSource" in entry:
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
    return False


def _calls(entries: List[Entry]) -> List[Dict[str, Any]]:
    """The usage of each distinct API call, in order (the last line of a call wins)."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        usage = message.get("usage")
        if not isinstance(usage, dict) or message.get("model") in SYNTHETIC_MODELS:
            continue
        key = message.get("id") or entry.get("requestId") or entry.get("uuid")
        if key:
            by_id.pop(key, None)
            by_id[key] = usage
    return list(by_id.values())


def _compaction(entries: List[Entry]) -> Optional[str]:
    trigger = None
    for entry in entries:
        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
            trigger = str((entry.get("compactMetadata") or {}).get("trigger") or "auto")
    if trigger is None:
        return None
    return "manual" if trigger == "manual" else "auto"


def answered_turns(entries: List[Entry]) -> List[Tuple[int, int]]:
    """``(start, end)`` index ranges of the turns that got at least one response."""
    starts = [i for i, e in enumerate(entries) if is_turn_start(e)]
    bounds = starts + [len(entries)]
    return [(bounds[n], bounds[n + 1]) for n in range(len(starts)) if _calls(entries[bounds[n] + 1 : bounds[n + 1]])]


def last_turn(entries: List[Entry]) -> Optional[Tuple[str, TurnMetrics]]:
    """The last answered turn's key and metrics, or ``None`` when nothing was answered."""
    turns = answered_turns(entries)
    if not turns:
        return None
    start, end = turns[-1]
    previous_end = turns[-2][1] if len(turns) > 1 else 0
    calls = _calls(entries[start + 1 : end])
    prompt = entries[start]
    metrics = TurnMetrics(fresh_session=len(turns) == 1, timestamp=str(prompt.get("timestamp") or ""))
    for usage in calls:
        metrics.input_tokens += int(usage.get("input_tokens") or 0)
        metrics.cache_read_tokens += int(usage.get("cache_read_input_tokens") or 0)
        metrics.cache_write_tokens += int(usage.get("cache_creation_input_tokens") or 0)
        metrics.output_tokens += int(usage.get("output_tokens") or 0)
    final = calls[-1]
    metrics.context_tokens = sum(
        int(final.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )
    # A compaction between the previous answered turn and this one renewed the context.
    metrics.compaction = _compaction(entries[previous_end:start])
    if metrics.compaction:
        metrics.fresh_session = False
    key = str(prompt.get("uuid") or prompt.get("promptId") or f"{prompt.get('timestamp', '')}:{start}")
    return key, metrics


def _assistant_text(entries: List[Entry]) -> str:
    return "".join(
        block.get("text", "")
        for entry in entries
        if entry.get("type") == "assistant"
        for block in ((entry.get("message") or {}).get("content") or [])
        if isinstance(block, dict) and block.get("type") == "text"
    )


def turn_is_flushed(entries: List[Entry], last_message: Optional[str]) -> bool:
    """Whether the transcript already holds the turn's final response."""
    starts = [i for i, e in enumerate(entries) if is_turn_start(e)]
    if not starts:
        return False
    assistants = [e for e in entries[starts[-1] + 1 :] if e.get("type") == "assistant"]
    if not assistants:
        return False
    if last_message:
        tail = last_message.strip()[-200:]
        if tail and tail in _assistant_text(assistants):
            return True
    return (assistants[-1].get("message") or {}).get("stop_reason") in FINAL_STOP_REASONS


def load_when_flushed(path: Path, last_message: Optional[str], timeout_s: float) -> List[Entry]:
    """Read the transcript, polling briefly until the final response lands.

    The Stop hook can fire before Claude Code has written the last assistant
    message to disk, so we give it up to ``timeout_s`` seconds.
    """
    deadline = time.monotonic() + max(timeout_s, 0.0)
    while True:
        entries = read_entries(path)
        if turn_is_flushed(entries, last_message) or time.monotonic() >= deadline:
            return entries
        time.sleep(0.15)
