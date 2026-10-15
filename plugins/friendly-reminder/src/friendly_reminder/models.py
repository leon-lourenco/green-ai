"""Plain data types shared by the rest of the package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set


@dataclass
class Usage:
    """Token counts for one or more API requests, split by billing class."""

    input: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    cache_read: int = 0
    output: int = 0

    @property
    def cache_write(self) -> int:
        return self.cache_write_5m + self.cache_write_1h

    @property
    def total(self) -> int:
        return self.input + self.cache_write + self.cache_read + self.output

    @property
    def prompt(self) -> int:
        """Tokens the model read on the way in (what long-context tiers key on)."""
        return self.input + self.cache_write + self.cache_read

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input=self.input + other.input,
            cache_write_5m=self.cache_write_5m + other.cache_write_5m,
            cache_write_1h=self.cache_write_1h + other.cache_write_1h,
            cache_read=self.cache_read + other.cache_read,
            output=self.output + other.output,
        )

    def to_dict(self) -> Dict[str, int]:
        return {
            "input": self.input,
            "cache_write_5m": self.cache_write_5m,
            "cache_write_1h": self.cache_write_1h,
            "cache_read": self.cache_read,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "Usage":
        return cls(**{k: int(data.get(k, 0) or 0) for k in cls().to_dict()})


@dataclass
class ApiCall:
    """One billed model request, as recorded in a Claude Code transcript."""

    message_id: str
    model: str
    usage: Usage
    speed: str = "standard"
    timestamp: str = ""


@dataclass
class Footprint:
    """Estimated environmental footprint."""

    wh: float = 0.0
    water_ml: float = 0.0

    def __add__(self, other: "Footprint") -> "Footprint":
        return Footprint(self.wh + other.wh, self.water_ml + other.water_ml)


@dataclass
class Totals:
    """Aggregated usage, cost and footprint for a turn, a day or a month."""

    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    footprint: Footprint = field(default_factory=Footprint)
    footprint_low: Footprint = field(default_factory=Footprint)
    footprint_high: Footprint = field(default_factory=Footprint)
    turns: int = 0
    models: Dict[str, int] = field(default_factory=dict)
    unpriced_models: Set[str] = field(default_factory=set)

    @property
    def cost_complete(self) -> bool:
        return not self.unpriced_models


@dataclass
class Quota:
    """Subscription quota snapshot cached locally by Claude Code."""

    plan: Optional[str] = None
    five_hour_pct: Optional[float] = None
    seven_day_pct: Optional[float] = None
    fetched_at_ms: Optional[int] = None
