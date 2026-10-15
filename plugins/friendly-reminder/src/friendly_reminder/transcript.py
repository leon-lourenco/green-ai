"""Read Claude Code session transcripts (JSONL) and extract the turn's API calls.

Transcript layout notes (Claude Code 2.1.x):

* One JSON object per line. ``type`` is ``user``, ``assistant`` or one of many
  bookkeeping types we ignore.
* A single API response is written as several ``assistant`` lines (one per
  content block) that repeat the same ``message.id`` and ``message.usage``, so
  calls must be de-duplicated by message id.
* Subagent transcripts live next to the session file in
  ``<session-id>/subagents/*.jsonl``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .models import ApiCall, Usage

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
    except FileNotFoundError:
        pass
    return entries


def subagent_transcripts(transcript_path: Path) -> List[Path]:
    folder = transcript_path.with_suffix("") / "subagents"
    return sorted(folder.glob("*.jsonl")) if folder.is_dir() else []


def is_turn_start(entry: Entry) -> bool:
    """True for the user line that opens a turn; false for tool results and meta lines.

    Current transcripts label turn-opening prompts with ``turnOrigin``/``origin``
    (a typed prompt, a task notification, a scheduled run...). Each of those ends
    in its own Stop event. Older transcripts have no labels, so we fall back to
    "a user line that is not a tool result".
    """
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


def turn_start_indexes(entries: List[Entry]) -> List[int]:
    return [i for i, e in enumerate(entries) if is_turn_start(e)]


def _usage_parts(usage: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """Yield the billed parts of a usage object.

    When the API reports ``iterations`` (compaction, advisor and similar
    multi-pass requests) the top-level numbers describe only the final pass,
    so the iterations are the complete record.
    """
    iterations = usage.get("iterations")
    if isinstance(iterations, list) and iterations:
        for part in iterations:
            if isinstance(part, dict):
                yield part
    else:
        yield usage


def parse_usage(raw: Dict[str, Any]) -> Usage:
    total = Usage()
    for part in _usage_parts(raw):
        written = int(part.get("cache_creation_input_tokens") or 0)
        split = part.get("cache_creation") or {}
        w1h = int(split.get("ephemeral_1h_input_tokens") or 0)
        w5m = int(split.get("ephemeral_5m_input_tokens") or 0)
        # Older transcripts have no TTL split: bill the rest at the 5-minute rate.
        w5m += max(written - w1h - w5m, 0)
        total = total + Usage(
            input=int(part.get("input_tokens") or 0),
            cache_write_5m=w5m,
            cache_write_1h=w1h,
            cache_read=int(part.get("cache_read_input_tokens") or 0),
            output=int(part.get("output_tokens") or 0),
        )
    return total


def iter_calls(entries: Iterable[Entry]) -> Iterator[ApiCall]:
    """Yield one ApiCall per distinct assistant message id (last line wins)."""
    by_id: Dict[str, ApiCall] = {}
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        usage = message.get("usage")
        model = message.get("model") or entry.get("requestedModel") or "unknown"
        if not isinstance(usage, dict) or model in SYNTHETIC_MODELS:
            continue
        key = message.get("id") or entry.get("requestId") or entry.get("uuid")
        if not key:
            continue
        by_id[key] = ApiCall(
            message_id=key,
            model=model,
            usage=parse_usage(usage),
            speed=str(usage.get("speed") or "standard"),
            timestamp=str(entry.get("timestamp") or ""),
        )
    return iter(by_id.values())


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
    starts = turn_start_indexes(entries)
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


def load_when_flushed(path: Path, last_message: Optional[str], timeout_s: float) -> Tuple[List[Entry], bool]:
    """Read the transcript, polling briefly until the final response lands.

    The Stop hook can fire before Claude Code has written the last assistant
    message to disk, so we give it up to ``timeout_s`` seconds.
    """
    deadline = time.monotonic() + max(timeout_s, 0.0)
    while True:
        entries = read_entries(path)
        if turn_is_flushed(entries, last_message):
            return entries, True
        if time.monotonic() >= deadline:
            return entries, False
        time.sleep(0.15)


def turn_calls(transcript_path: Path, entries: List[Entry]) -> Tuple[List[ApiCall], Optional[Entry]]:
    """Calls made since the turn's opening prompt (subagents included), and that prompt."""
    starts = turn_start_indexes(entries)
    if not starts:
        return [], None
    prompt = entries[starts[-1]]
    since = str(prompt.get("timestamp") or "")
    calls: Dict[str, ApiCall] = {c.message_id: c for c in iter_calls(entries[starts[-1] + 1 :])}
    for sub in subagent_transcripts(transcript_path):
        for call in iter_calls(read_entries(sub)):
            # ISO-8601 UTC timestamps compare correctly as strings.
            if call.timestamp and since and call.timestamp >= since:
                calls.setdefault(call.message_id, call)
    return list(calls.values()), prompt
