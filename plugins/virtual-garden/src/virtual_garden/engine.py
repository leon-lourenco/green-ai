"""How the garden grows: XP, sunlight, soil, unlocks and badges.

The rules reward habits that make AI cheaper to run, never punish:

* Sunlight (vitality) follows prompt caching. A cached prompt costs a
  fraction of the compute of a fresh one.
* Soil follows the context size. Every call re-reads the whole context, so a
  lean context saves energy; ``/compact`` or a new session renews the soil.
* The plant grows on every answered turn, faster with good sun and soil, and
  at half speed while either is below ``SLOW_BELOW``.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from .models import Event, GardenState, TurnMetrics
from .species import SPECIES, STAGES

STAGE_XP: List[int] = [0, 100, 300, 700, 1500, 3000]  # XP where each stage starts

BASE_XP = 10
CACHE_TIERS: List[Tuple[float, int, int]] = [  # (ratio at least, XP bonus, vitality change)
    (0.90, 20, 8),
    (0.75, 10, 4),
    (0.40, 5, 0),
    (0.00, 0, -6),
]
FRESH_SESSION_XP = 5  # a new session has nothing cached yet; it is not judged
MANUAL_COMPACT_XP = 30
LEAN_CONTEXT_TOKENS = 40_000
LEAN_XP = 5
SOIL_TIERS: List[Tuple[int, int, int]] = [  # (context above, soil change, floor)
    (120_000, -15, 20),
    (80_000, -8, 40),
    (LEAN_CONTEXT_TOKENS, -3, 60),
]
SOIL_RECOVERY = 3
VITALITY_FLOOR = 20
REST_HOURS = 1.0
REST_VITALITY = 10
SLOW_BELOW = 40

SUNNY_STREAK = 5  # turns in a row with cache >= GOOD_CACHE
GOOD_CACHE = 0.75
LIGHT_STREAK = 10  # turns in a row under LEAN_CONTEXT_TOKENS

BADGES: List[str] = ["pruner", "sunny", "light", "master", "collector"]


def stage_for_xp(xp: int) -> int:
    return max(n + 1 for n, start in enumerate(STAGE_XP) if xp >= start)


def stage_progress(xp: int) -> Tuple[int, Optional[int]]:
    """XP earned in the current stage and the XP the stage needs, ``None`` at the last one."""
    stage = stage_for_xp(xp)
    if stage >= STAGES:
        return xp - STAGE_XP[-1], None
    return xp - STAGE_XP[stage - 1], STAGE_XP[stage] - STAGE_XP[stage - 1]


def unlock_rule_met(species: str, state: GardenState) -> bool:
    if species == "cactus":
        return any(stage_for_xp(xp) >= 3 for xp in state.plants.values())
    if species == "sakura":
        return "sunny" in state.badges
    if species == "ipe":
        return "pruner" in state.badges or "light" in state.badges
    return True


def _hours_between(earlier: str, later: str) -> float:
    try:
        then = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
        now = datetime.fromisoformat(later.replace("Z", "+00:00"))
        return (now - then).total_seconds() / 3600
    except (ValueError, TypeError):  # unparsable, or one naive and one aware
        return 0.0


def grow(state: GardenState, turn: TurnMetrics) -> List[Event]:
    """Apply one answered turn to the garden, in place, and return what to celebrate."""
    events: List[Event] = []
    stage_before = stage_for_xp(state.xp)
    xp = BASE_XP

    if state.last_turn_at and turn.timestamp and _hours_between(state.last_turn_at, turn.timestamp) >= REST_HOURS:
        state.vitality = min(100, state.vitality + REST_VITALITY)

    if turn.fresh_session:
        xp += FRESH_SESSION_XP
    else:
        ratio = turn.cache_ratio
        bonus, change = next((b, c) for at_least, b, c in CACHE_TIERS if ratio >= at_least)
        xp += bonus
        state.vitality = max(VITALITY_FLOOR, min(100, state.vitality + change))
        state.cache_streak = state.cache_streak + 1 if ratio >= GOOD_CACHE else 0

    if turn.compaction or turn.fresh_session:
        state.soil = 100
        if turn.compaction == "manual":
            xp += MANUAL_COMPACT_XP
            _award(state, "pruner", events)
    else:
        tier = next(((c, floor) for above, c, floor in SOIL_TIERS if turn.context_tokens > above), None)
        if tier:
            change, floor = tier
            state.soil = max(min(state.soil, floor), state.soil + change)  # never below the floor, nor raised to it
        else:
            state.soil = min(100, state.soil + SOIL_RECOVERY)
    if turn.context_tokens and turn.context_tokens < LEAN_CONTEXT_TOKENS:
        xp += LEAN_XP
        state.lean_streak += 1
    else:
        state.lean_streak = 0

    if min(state.vitality, state.soil) < SLOW_BELOW:
        xp //= 2

    state.plants[state.species] = state.xp + xp
    state.turns += 1
    if turn.timestamp:
        state.last_turn_at = turn.timestamp

    stage_after = stage_for_xp(state.xp)
    if stage_after > stage_before:
        events.append(Event("level_up", str(stage_after), state.species))
    if state.cache_streak >= SUNNY_STREAK:
        _award(state, "sunny", events)
    if state.lean_streak >= LIGHT_STREAK:
        _award(state, "light", events)
    if stage_after >= STAGES:
        _award(state, "master", events)
    for species in SPECIES:
        if species not in state.unlocked and unlock_rule_met(species, state):
            state.unlocked.append(species)
            state.plants.setdefault(species, 0)
            events.append(Event("unlock", species))
    state.unlocked.sort(key=SPECIES.index)
    if len(state.unlocked) == len(SPECIES):
        _award(state, "collector", events)
    return events


def _award(state: GardenState, badge: str, events: List[Event]) -> None:
    if badge not in state.badges:
        state.badges.append(badge)
        events.append(Event("badge", badge))


def switch(state: GardenState, species: str) -> bool:
    """Tend another unlocked species; each keeps its own growth."""
    if species not in state.unlocked:
        return False
    state.species = species
    state.plants.setdefault(species, 0)
    return True
