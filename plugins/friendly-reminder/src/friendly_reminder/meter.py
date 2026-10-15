"""Aggregate a turn's API calls into priced, footprint-estimated totals."""

from __future__ import annotations

from typing import Iterable

from .footprint import FootprintModel
from .models import ApiCall, Totals
from .pricing import PriceBook, normalize_model


def aggregate(
    calls: Iterable[ApiCall],
    prices: PriceBook,
    footprint: FootprintModel,
    profile: str = "central",
    water_scope: str = "full",
) -> Totals:
    totals = Totals(turns=1)
    for call in calls:
        totals.usage = totals.usage + call.usage
        name = normalize_model(call.model)
        totals.models[name] = totals.models.get(name, 0) + call.usage.total

        cost = prices.cost(call)
        if cost is None:
            totals.unpriced_models.add(name)
        else:
            totals.cost_usd += cost

        totals.footprint = totals.footprint + footprint.estimate(call.usage, profile, water_scope)
        totals.footprint_low = totals.footprint_low + footprint.estimate(call.usage, "low", water_scope)
        totals.footprint_high = totals.footprint_high + footprint.estimate(call.usage, "high", water_scope)
    return totals
