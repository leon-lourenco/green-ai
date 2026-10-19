"""Shared test helpers: put ``src`` on the path and build transcripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def write_jsonl(path: Path, entries: List[Dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
    return path


def prompt(uuid: str, text: str = "hi", timestamp: str = "2026-10-18T10:00:00Z") -> Dict[str, Any]:
    return {"type": "user", "uuid": uuid, "timestamp": timestamp, "message": {"role": "user", "content": text}}


def tool_result(uuid: str) -> Dict[str, Any]:
    content = [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]
    return {"type": "user", "uuid": uuid, "message": {"role": "user", "content": content}}


def reply(
    msg_id: str,
    fresh: int = 0,
    cached: int = 0,
    written: int = 0,
    out: int = 10,
    stop: Optional[str] = "end_turn",
    text: str = "done",
) -> Dict[str, Any]:
    usage = {
        "input_tokens": fresh,
        "cache_read_input_tokens": cached,
        "cache_creation_input_tokens": written,
        "output_tokens": out,
    }
    message = {
        "id": msg_id,
        "model": "claude-opus-5-5",
        "usage": usage,
        "stop_reason": stop,
        "content": [{"type": "text", "text": text}],
    }
    return {"type": "assistant", "message": message}


def compact_boundary(trigger: str = "manual") -> Dict[str, Any]:
    return {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": trigger}}
