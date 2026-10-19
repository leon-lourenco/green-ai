"""The garden file, shared by every session and tool.

Every change is a read-modify-write under an exclusive lock, so two sessions
finishing a turn at once never lose each other's growth. A turn is recorded
under a key both the hook and a manual run derive the same way, and is
applied only once.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from .engine import grow, switch
from .models import SEEN_TURNS_KEPT, Event, GardenState, TurnMetrics

try:
    import fcntl
except ImportError:  # Windows: no lock; the write itself is still atomic
    fcntl = None  # type: ignore[assignment]

STATE_FILENAME = "garden-state.json"
LOCK_FILENAME = "garden-state.lock"


def load_state(folder: Path) -> GardenState:
    try:
        data = json.loads((folder / STATE_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return GardenState()
    return GardenState.from_dict(data) if isinstance(data, dict) else GardenState()


def save_state(state: GardenState, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=str(folder), delete=False, encoding="utf-8", suffix=".tmp") as handle:
        handle.write(text)
    os.replace(handle.name, folder / STATE_FILENAME)


@contextmanager
def editing(folder: Path) -> Iterator[GardenState]:
    """Load the garden under an exclusive lock and save it when the block ends."""
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / LOCK_FILENAME).open("a") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = load_state(folder)
            yield state
            save_state(state, folder)
        finally:
            if fcntl:
                fcntl.flock(lock, fcntl.LOCK_UN)


def record_turn(
    folder: Path, key: str, turn: Optional[TurnMetrics], species: Optional[str] = None
) -> Tuple[GardenState, List[Event]]:
    """Apply a turn once and return the garden with the turn's events.

    ``species`` is the plant the settings ask for; it is tended from this turn
    on when it is unlocked. Seeing the latest turn again returns its events
    again, so a redraw still shows them.
    """
    with editing(folder) as state:
        if species:
            switch(state, species)
        if turn is None:
            return state, []
        if key in state.seen_turns:
            latest = state.seen_turns and state.seen_turns[-1] == key
            return state, [Event.from_dict(e) for e in state.last_events] if latest else []
        events = grow(state, turn)
        state.seen_turns = (state.seen_turns + [key])[-SEEN_TURNS_KEPT:]
        state.last_events = [e.to_dict() for e in events]
        return state, events
