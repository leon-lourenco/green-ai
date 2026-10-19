"""The garden file: persistence, migration and counting each turn once."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401 - puts src on the path
from virtual_garden.models import GardenState, TurnMetrics
from virtual_garden.state import STATE_FILENAME, load_state, record_turn, save_state


def turn() -> TurnMetrics:
    return TurnMetrics(input_tokens=50, cache_read_tokens=950, context_tokens=1000)


class StateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_round_trip(self) -> None:
        state = GardenState(species="cactus", plants={"bonsai": 400, "cactus": 20}, unlocked=["bonsai", "cactus"])
        save_state(state, self.folder)
        loaded = load_state(self.folder)
        self.assertEqual(loaded.species, "cactus")
        self.assertEqual(loaded.plants, {"bonsai": 400, "cactus": 20})

    def test_missing_or_broken_file_gives_a_new_garden(self) -> None:
        self.assertEqual(load_state(self.folder).xp, 0)
        (self.folder / STATE_FILENAME).write_text("{not json", encoding="utf-8")
        self.assertEqual(load_state(self.folder).species, "bonsai")

    def test_reads_a_v0_file(self) -> None:
        v0 = {
            "species": "sakura",
            "unlocked_species": ["bonsai", "sakura"],
            "stage": 3,
            "xp": 350,
            "vitality": 85,
            "soil_health": 60,
            "turns_count": 12,
            "high_cache_streak": 2,
            "badges": ["cache_sun", "master_gardener"],
        }
        (self.folder / STATE_FILENAME).write_text(json.dumps(v0), encoding="utf-8")
        state = load_state(self.folder)
        self.assertEqual(state.species, "sakura")
        self.assertEqual(state.plants, {"sakura": 350})
        self.assertEqual(state.soil, 60)
        self.assertEqual(state.turns, 12)
        self.assertEqual(state.badges, ["sunny", "master"])

    def test_unknown_species_falls_back_to_the_starter(self) -> None:
        state = GardenState.from_dict({"version": 1, "species": "orchid", "unlocked": ["orchid"]})
        self.assertEqual(state.species, "bonsai")
        self.assertEqual(state.unlocked, ["bonsai"])

    def test_a_turn_counts_once(self) -> None:
        first, events = record_turn(self.folder, "claude:s:1", turn())
        again, replayed = record_turn(self.folder, "claude:s:1", turn())
        self.assertEqual(first.xp, again.xp)
        self.assertEqual(again.turns, 1)
        self.assertEqual([e.to_dict() for e in replayed], [e.to_dict() for e in events])

    def test_an_older_turn_replays_no_events(self) -> None:
        record_turn(self.folder, "a", TurnMetrics(compaction="manual"))
        record_turn(self.folder, "b", turn())
        state, events = record_turn(self.folder, "a", TurnMetrics(compaction="manual"))
        self.assertEqual(events, [])
        self.assertEqual(state.turns, 2)

    def test_requested_species_is_tended_once_unlocked(self) -> None:
        state, _ = record_turn(self.folder, "a", turn(), species="cactus")
        self.assertEqual(state.species, "bonsai")
        save_state(GardenState(unlocked=["bonsai", "cactus"]), self.folder)
        record_turn(self.folder, "b", None, species="cactus")
        self.assertEqual(load_state(self.folder).species, "cactus")


if __name__ == "__main__":
    unittest.main()
