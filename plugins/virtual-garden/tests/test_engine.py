"""The rules of growth."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401 - puts src on the path
from virtual_garden.engine import (
    BASE_XP,
    LIGHT_STREAK,
    SUNNY_STREAK,
    grow,
    stage_for_xp,
    stage_progress,
    switch,
)
from virtual_garden.models import GardenState, TurnMetrics


def cached_turn(ratio: float = 0.95, context: int = 20_000, **kwargs) -> TurnMetrics:
    cached = int(1000 * ratio)
    return TurnMetrics(input_tokens=1000 - cached, cache_read_tokens=cached, context_tokens=context, **kwargs)


class StageTests(unittest.TestCase):
    def test_stage_thresholds(self) -> None:
        cases = {0: 1, 99: 1, 100: 2, 299: 2, 300: 3, 700: 4, 1500: 5, 3000: 6, 99999: 6}
        for xp, stage in cases.items():
            self.assertEqual(stage_for_xp(xp), stage, xp)

    def test_progress_within_stage(self) -> None:
        self.assertEqual(stage_progress(150), (50, 200))
        self.assertEqual(stage_progress(3200), (200, None))


class GrowTests(unittest.TestCase):
    def test_good_cache_and_lean_context(self) -> None:
        state = GardenState(vitality=80)
        grow(state, cached_turn(0.95))
        self.assertEqual(state.xp, BASE_XP + 20 + 5)
        self.assertEqual(state.vitality, 88)
        self.assertEqual(state.cache_streak, 1)
        self.assertEqual(state.turns, 1)

    def test_cache_write_counts_as_uncached(self) -> None:
        turn = TurnMetrics(cache_read_tokens=500, cache_write_tokens=500)
        self.assertAlmostEqual(turn.cache_ratio, 0.5)

    def test_poor_cache_dims_the_sun_down_to_a_floor(self) -> None:
        state = GardenState(vitality=24, cache_streak=3)
        grow(state, cached_turn(0.1))
        self.assertEqual(state.vitality, 20)
        self.assertEqual(state.cache_streak, 0)

    def test_fresh_session_is_not_judged_and_renews_soil(self) -> None:
        state = GardenState(vitality=70, soil=30)
        grow(state, TurnMetrics(input_tokens=5000, context_tokens=5000, fresh_session=True))
        self.assertEqual(state.vitality, 70)
        self.assertEqual(state.soil, 100)

    def test_soil_dries_with_large_context_but_not_below_floor(self) -> None:
        state = GardenState(soil=100)
        grow(state, cached_turn(context=90_000))
        self.assertEqual(state.soil, 92)
        state.soil = 42
        grow(state, cached_turn(context=90_000))
        self.assertEqual(state.soil, 40)
        state.soil = 30  # already below the 80k floor: left alone
        grow(state, cached_turn(context=90_000))
        self.assertEqual(state.soil, 30)

    def test_small_context_recovers_soil(self) -> None:
        state = GardenState(soil=90)
        grow(state, cached_turn(context=10_000))
        self.assertEqual(state.soil, 93)

    def test_manual_compact_rewards_and_auto_only_renews(self) -> None:
        manual = GardenState(soil=40)
        events = grow(manual, cached_turn(compaction="manual", context=8_000))
        self.assertEqual(manual.soil, 100)
        self.assertIn("pruner", manual.badges)
        self.assertIn(("badge", "pruner"), [(e.kind, e.value) for e in events])
        self.assertIn("ipe", manual.unlocked)

        auto = GardenState(soil=40)
        grow(auto, cached_turn(compaction="auto", context=8_000))
        self.assertEqual(auto.soil, 100)
        self.assertNotIn("pruner", auto.badges)
        self.assertLess(auto.xp, manual.xp)

    def test_slow_growth_when_sun_or_soil_is_low(self) -> None:
        healthy, dry = GardenState(), GardenState(soil=30)
        grow(healthy, cached_turn(context=200_000))
        grow(dry, cached_turn(context=200_000))
        self.assertEqual(dry.xp, healthy.xp // 2)

    def test_rest_restores_sunlight(self) -> None:
        state = GardenState(vitality=50, last_turn_at="2026-10-18T08:00:00Z")
        grow(state, cached_turn(0.5, timestamp="2026-10-18T10:00:00Z"))
        self.assertEqual(state.vitality, 60)
        self.assertEqual(state.last_turn_at, "2026-10-18T10:00:00Z")

    def test_level_up_event(self) -> None:
        state = GardenState(plants={"bonsai": 95})
        events = grow(state, cached_turn())
        self.assertIn(("level_up", "2", "bonsai"), [(e.kind, e.value, e.species) for e in events])


class UnlockTests(unittest.TestCase):
    def test_cactus_unlocks_at_sapling(self) -> None:
        state = GardenState(plants={"bonsai": 290})
        events = grow(state, cached_turn())
        self.assertIn("cactus", state.unlocked)
        self.assertIn(("unlock", "cactus"), [(e.kind, e.value) for e in events])
        self.assertEqual(state.plants["cactus"], 0)

    def test_sakura_unlocks_with_a_sunny_streak(self) -> None:
        state = GardenState()
        for _ in range(SUNNY_STREAK):
            grow(state, cached_turn(0.8))
        self.assertIn("sunny", state.badges)
        self.assertIn("sakura", state.unlocked)

    def test_ipe_unlocks_with_a_light_streak(self) -> None:
        state = GardenState()
        for _ in range(LIGHT_STREAK):
            grow(state, cached_turn(0.5, context=10_000))
        self.assertIn("light", state.badges)
        self.assertIn("ipe", state.unlocked)

    def test_collector_and_master(self) -> None:
        state = GardenState(plants={"bonsai": 2990}, unlocked=["bonsai", "cactus", "sakura"], badges=["sunny"])
        grow(state, cached_turn(compaction="manual"))
        self.assertIn("master", state.badges)
        self.assertIn("collector", state.badges)
        self.assertEqual(state.unlocked, ["bonsai", "cactus", "sakura", "ipe"])

    def test_each_species_keeps_its_growth(self) -> None:
        state = GardenState(plants={"bonsai": 500}, unlocked=["bonsai", "cactus"])
        self.assertTrue(switch(state, "cactus"))
        grow(state, cached_turn())
        self.assertEqual(state.plants["bonsai"], 500)
        self.assertGreater(state.plants["cactus"], 0)
        self.assertFalse(switch(state, "sakura"))
        self.assertEqual(state.species, "cactus")


if __name__ == "__main__":
    unittest.main()
