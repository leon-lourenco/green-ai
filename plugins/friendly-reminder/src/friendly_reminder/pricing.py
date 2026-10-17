"""API list prices and per-call cost."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ApiCall

PER_TOKEN = 1_000_000.0

_DATE_SUFFIX = re.compile(r"-\d{8}$")
_BEDROCK_SUFFIX = re.compile(r"-v\d+(:\d+)?$")


def normalize_model(name: str) -> str:
    """Map transcript / provider model ids onto the first-party id.

    ``us.anthropic.claude-opus-5-5-v1:0`` -> ``claude-opus-5-5``,
    ``claude-opus-4-5@20251101`` -> ``claude-opus-4-5``,
    ``claude-sonnet-5[1m]`` -> ``claude-sonnet-5``,
    ``Gemini 3.8 Flash (High)`` -> ``gemini-3.8-flash``.
    """
    model = name.strip().lower()
    model = re.sub(r"\[.*?\]", "", model)
    model = re.sub(r"\(.*?\)", "", model).strip()
    if "anthropic." in model:
        model = model.split("anthropic.", 1)[1]
    if "google." in model:
        model = model.split("google.", 1)[1]
    model = model.split("@", 1)[0]
    model = _BEDROCK_SUFFIX.sub("", model)
    model = _DATE_SUFFIX.sub("", model)
    if " " in model:
        model = re.sub(r"\s+", "-", model)
    return model


@dataclass(frozen=True)
class Rates:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


class PriceBook:
    def __init__(self, data: Dict[str, Any]):
        self.as_of: str = str(data.get("as_of", "unknown"))
        self.source: str = str(data.get("source", ""))
        defaults = data.get("defaults") or {}
        self._w5m = float(defaults.get("cache_write_5m_multiplier", 1.25))
        self._w1h = float(defaults.get("cache_write_1h_multiplier", 2.0))
        self._models: Dict[str, Dict[str, Any]] = dict(data.get("models") or {})

    @classmethod
    def load(cls, bundled: Path, override: Optional[Path] = None) -> "PriceBook":
        data = json.loads(bundled.read_text(encoding="utf-8"))
        if override and override.is_file():
            extra = json.loads(override.read_text(encoding="utf-8"))
            data.setdefault("models", {}).update(extra.get("models") or {})
            for key in ("as_of", "source", "defaults"):
                if key in extra:
                    data[key] = extra[key]
        return cls(data)

    def entry(self, model: str) -> Optional[Dict[str, Any]]:
        key = normalize_model(model)
        if key in self._models:
            return self._models[key]
        # Longest known id that prefixes the model, e.g. a future dated snapshot.
        matches = [k for k in self._models if key.startswith(k + "-")]
        return self._models[max(matches, key=len)] if matches else None

    def knows(self, model: str) -> bool:
        return self.entry(model) is not None

    def rates(self, call: ApiCall) -> Optional[Rates]:
        entry = self.entry(call.model)
        if entry is None:
            return None
        base_in = float(entry["input"])
        base_out = float(entry["output"])
        read = float(entry.get("cache_read", base_in * 0.1))

        tier = entry.get("long_context")
        if tier and call.usage.prompt > int(tier.get("above_prompt_tokens", 0)):
            base_in, base_out = float(tier["input"]), float(tier["output"])
            read = float(tier.get("cache_read", base_in * 0.1))

        fast = entry.get("fast")
        if fast and call.speed == "fast":
            factor = float(fast["input"]) / base_in if base_in else 1.0
            base_in, base_out = float(fast["input"]), float(fast["output"])
            read *= factor

        return Rates(
            input=base_in,
            output=base_out,
            cache_read=read,
            cache_write_5m=base_in * self._w5m,
            cache_write_1h=base_in * self._w1h,
        )

    def cost(self, call: ApiCall) -> Optional[float]:
        rates = self.rates(call)
        if rates is None:
            return None
        u = call.usage
        return (
            u.input * rates.input
            + u.output * rates.output
            + u.cache_read * rates.cache_read
            + u.cache_write_5m * rates.cache_write_5m
            + u.cache_write_1h * rates.cache_write_1h
        ) / PER_TOKEN
