"""Measuring the last answered turn of a Claude Code transcript."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import compact_boundary, prompt, reply, tool_result, write_jsonl
from virtual_garden.transcript import last_turn, load_when_flushed, read_entries


class TranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "session.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def measure(self, entries):
        return last_turn(read_entries(write_jsonl(self.path, entries)))

    def test_sums_calls_and_takes_context_from_the_last_one(self) -> None:
        key, turn = self.measure([
            prompt("p1"),
            reply("m1", fresh=1000, written=20_000),
            prompt("p2", timestamp="2026-10-18T10:05:00Z"),
            reply("m2", fresh=100, cached=21_000, stop="tool_use"),
            reply("m2", fresh=100, cached=21_000, stop="tool_use"),  # same call, second content block
            tool_result("r1"),
            reply("m3", fresh=200, cached=21_500, written=300),
        ])
        self.assertEqual(key, "p2")
        self.assertEqual(turn.input_tokens, 300)
        self.assertEqual(turn.cache_read_tokens, 42_500)
        self.assertEqual(turn.cache_write_tokens, 300)
        self.assertEqual(turn.context_tokens, 22_000)
        self.assertFalse(turn.fresh_session)
        self.assertIsNone(turn.compaction)
        self.assertEqual(turn.timestamp, "2026-10-18T10:05:00Z")

    def test_first_turn_is_a_fresh_session(self) -> None:
        _, turn = self.measure([prompt("p1"), reply("m1", fresh=5000)])
        self.assertTrue(turn.fresh_session)

    def test_unanswered_prompt_is_skipped(self) -> None:
        key, _ = self.measure([prompt("p1"), reply("m1", fresh=5), prompt("p2")])
        self.assertEqual(key, "p1")

    def test_nothing_answered(self) -> None:
        self.assertIsNone(self.measure([prompt("p1")]))
        self.assertIsNone(self.measure([]))

    def test_compaction_before_the_turn(self) -> None:
        for trigger in ("manual", "auto"):
            _, turn = self.measure([
                prompt("p1"),
                reply("m1", fresh=90_000),
                prompt("c", text="<command-name>/compact</command-name>"),
                compact_boundary(trigger),
                {"type": "user", "isCompactSummary": True, "message": {"content": "summary"}},
                prompt("p2"),
                reply("m2", fresh=6_000),
            ])
            self.assertEqual(turn.compaction, trigger)
            self.assertFalse(turn.fresh_session)

    def test_compaction_is_not_counted_on_later_turns(self) -> None:
        _, turn = self.measure([
            prompt("p1"), reply("m1", fresh=5),
            compact_boundary(),
            prompt("p2"), reply("m2", fresh=5),
            prompt("p3"), reply("m3", fresh=5),
        ])
        self.assertIsNone(turn.compaction)

    def test_load_when_flushed_returns_at_once_when_complete(self) -> None:
        write_jsonl(self.path, [prompt("p1"), reply("m1", text="all done")])
        entries = load_when_flushed(self.path, "all done", timeout_s=5)
        self.assertEqual(len(entries), 2)


if __name__ == "__main__":
    unittest.main()
