"""Energy and water estimates from token counts.

Every number here is an estimate built from published research, not a
measurement of Anthropic's infrastructure. ``data/footprint.json`` holds the
factors and their sources.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .models import Footprint, Usage

PROFILES = ("low", "central", "high")
WATER_SCOPES = ("full", "onsite")


class FootprintModel:
    def __init__(self, data: Dict[str, Any]):
        self.as_of = str(data.get("as_of", "unknown"))
        self.profiles: Dict[str, Dict[str, Any]] = data["profiles"]
        self.sources = data.get("sources") or []
        self.assumptions = data.get("assumptions") or []

    @classmethod
    def load(cls, bundled: Path, override: Optional[Path] = None) -> FootprintModel:
        data = json.loads(bundled.read_text(encoding="utf-8"))
        if override and override.is_file():
            extra = json.loads(override.read_text(encoding="utf-8"))
            for name, profile in (extra.get("profiles") or {}).items():
                data["profiles"].setdefault(name, {}).update(profile)
        return cls(data)

    def estimate(self, usage: Usage, profile: str = "central", water_scope: str = "full") -> Footprint:
        p = self.profiles[profile]
        per_1k = p["wh_per_1k"]
        it_wh = (
            usage.output * per_1k["output"]
            + usage.input * per_1k["input"]
            + usage.cache_write * per_1k["cache_write"]
            + usage.cache_read * per_1k["cache_read"]
        ) / 1000.0
        wh = it_wh * float(p["pue"])
        litres_per_kwh = float(p["wue_onsite_l_per_kwh"])
        if water_scope == "full":
            litres_per_kwh += float(p["ewif_offsite_l_per_kwh"])
        # Wh * (L/kWh) = mL
        return Footprint(wh=wh, water_ml=wh * litres_per_kwh)
