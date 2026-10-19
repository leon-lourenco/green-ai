"""Data models for Virtual Garden."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .species import SPECIES, STARTER


@dataclass
class TurnMetrics:
    """What one answered turn tells the garden.

    Token counts are summed over the turn's API calls; ``context_tokens`` is
    the prompt size of its last call, which is how full the context window is.
    """

    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    context_tokens: int = 0
    compaction: Optional[str] = None  # "manual" or "auto" when the context was compacted before this turn
    fresh_session: bool = False  # the session's first answered turn
    timestamp: str = ""

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def cache_ratio(self) -> float:
        prompt = self.prompt_tokens
        return self.cache_read_tokens / prompt if prompt > 0 else 0.0


@dataclass
class Event:
    """Something worth celebrating that happened on a turn."""

    kind: str  # "level_up", "unlock", "badge"
    value: str  # the stage number, species or badge
    species: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        return cls(str(data.get("kind", "")), str(data.get("value", "")), str(data.get("species", "")))


SEEN_TURNS_KEPT = 500


@dataclass
class GardenState:
    """The garden, shared by every session and tool."""

    species: str = STARTER  # the plant being tended
    plants: Dict[str, int] = field(default_factory=lambda: {STARTER: 0})  # XP per species
    unlocked: List[str] = field(default_factory=lambda: [STARTER])
    vitality: int = 100  # sunlight: prompt caching
    soil: int = 100  # freshness of the context
    turns: int = 0
    cache_streak: int = 0  # turns in a row with a good cache hit rate
    lean_streak: int = 0  # turns in a row with a small context
    badges: List[str] = field(default_factory=list)
    last_turn_at: str = ""
    seen_turns: List[str] = field(default_factory=list)  # recent turn keys, so a turn counts once
    last_events: List[Dict[str, str]] = field(default_factory=list)  # events of seen_turns[-1]

    @property
    def xp(self) -> int:
        return self.plants.get(self.species, 0)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["version"] = 1
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GardenState:
        if "version" not in data:
            data = _from_v0(data)
        state = cls()
        for key in cls.__dataclass_fields__:
            if key in data:
                setattr(state, key, data[key])
        state.unlocked = [s for s in SPECIES if s in state.unlocked or s == STARTER]
        state.plants = {s: int(xp) for s, xp in state.plants.items() if s in SPECIES}
        if state.species not in state.unlocked:
            state.species = STARTER
        state.plants.setdefault(state.species, 0)
        return state


V0_BADGES = {"pruner": "pruner", "cache_sun": "sunny", "master_gardener": "master"}


def _from_v0(data: Dict[str, Any]) -> Dict[str, Any]:
    """Read a 0.1.0 state file: one XP pool, ``unlocked_species``, ``soil_health``."""
    species = str(data.get("species") or STARTER)
    return {
        "species": species,
        "plants": {species: int(data.get("xp") or 0)},
        "unlocked": list(data.get("unlocked_species") or [STARTER]),
        "vitality": int(data.get("vitality", 100)),
        "soil": int(data.get("soil_health", 100)),
        "turns": int(data.get("turns_count") or 0),
        "cache_streak": int(data.get("high_cache_streak") or 0),
        "badges": [V0_BADGES[b] for b in data.get("badges") or [] if b in V0_BADGES],
    }
