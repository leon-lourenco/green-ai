"""Drawing the garden."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401 - puts src on the path
from virtual_garden.engine import STAGE_XP
from virtual_garden.models import Event, GardenState
from virtual_garden.render import INNER, notes_for, render_full, render_summary, width, wrap
from virtual_garden.species import ART, SPECIES, STAGES, sprite


class WidthTests(unittest.TestCase):
    def test_terminal_columns(self) -> None:
        self.assertEqual(width("abc"), 3)
        self.assertEqual(width("🌱"), 2)
        self.assertEqual(width("☀️"), 2)  # narrow symbol + emoji selector
        self.assertEqual(width("🪴"), 2)
        self.assertEqual(width("Ipê"), 3)

    def test_wrap_breaks_on_spaces(self) -> None:
        lines = wrap("Large context? Consider pruning old turns with /compact.", 20)
        self.assertTrue(all(width(line) <= 20 for line in lines))
        self.assertIn("pruning", " ".join(lines).split())


class SpriteTests(unittest.TestCase):
    def test_every_species_has_every_stage(self) -> None:
        for species in SPECIES:
            self.assertEqual(len(ART[species]), STAGES, species)

    def test_sprites_fit_the_box(self) -> None:
        for species in SPECIES:
            for stage in range(1, STAGES + 1):
                self.assertLessEqual(max(width(line) for line in sprite(species, stage)), INNER, (species, stage))

    def test_stage_is_clamped(self) -> None:
        self.assertEqual(sprite("bonsai", 0), sprite("bonsai", 1))
        self.assertEqual(sprite("bonsai", 9), sprite("bonsai", STAGES))


class BoxTests(unittest.TestCase):
    def test_every_line_has_the_same_width(self) -> None:
        notes = ["🎉 A long celebration note that has to wrap onto a second line inside the box."]
        for lang in ("en", "pt"):
            for species in SPECIES:
                for xp in STAGE_XP:
                    state = GardenState(
                        species=species,
                        plants={s: xp for s in SPECIES},
                        unlocked=list(SPECIES),
                        badges=["pruner", "sunny", "light", "master", "collector"],
                        soil=30,
                    )
                    lines = render_full(state, lang, notes, seed="x")
                    widths = {width(line) for line in lines}
                    self.assertEqual(widths, {INNER + 2}, (lang, species, xp, lines))

    def test_portuguese_has_no_english_labels(self) -> None:
        text = "\n".join(render_full(GardenState(), "pt", seed="x"))
        for word in ("Growth", "Soil", "Sun", "Turns", "Seed"):
            self.assertNotIn(word, text)
        self.assertIn("Semente", text)

    def test_summary(self) -> None:
        state = GardenState(plants={"bonsai": 120}, vitality=90)
        line = render_summary(state, "en")[0]
        self.assertIn("Sprout", line)
        self.assertIn("20/200 XP", line)
        self.assertIn("90%", line)

    def test_last_stage_shows_total_xp(self) -> None:
        state = GardenState(plants={"bonsai": 4000})
        self.assertIn("4000 XP", render_summary(state, "en")[0])


class NotesTests(unittest.TestCase):
    def test_events_and_locked_species(self) -> None:
        state = GardenState()
        events = [Event("level_up", "2", "bonsai"), Event("unlock", "cactus"), Event("badge", "pruner")]
        notes = notes_for(state, events, "sakura", "en")
        self.assertEqual(len(notes), 4)
        self.assertIn("Sprout", notes[0])
        self.assertIn("Cactus", notes[1])
        self.assertIn("Pruner", notes[2])
        self.assertIn("locked", notes[3])

    def test_unlocked_species_needs_no_hint(self) -> None:
        state = GardenState(unlocked=["bonsai", "cactus"])
        self.assertEqual(notes_for(state, [], "cactus", "pt"), [])


if __name__ == "__main__":
    unittest.main()
