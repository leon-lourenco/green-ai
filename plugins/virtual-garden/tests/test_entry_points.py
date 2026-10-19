"""The Claude Code hook, the agy adapter and the manual commands."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import prompt, reply, write_jsonl
from virtual_garden import hook
from virtual_garden.adapters import agy
from virtual_garden.models import GardenState
from virtual_garden.state import load_state, save_state


class Pipe(io.StringIO):
    def isatty(self) -> bool:
        return False


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


class GardenCase(unittest.TestCase):
    """A throwaway home and garden folder for each test."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        env = {"VIRTUAL_GARDEN_DATA": str(self.data), "CLAUDE_PLUGIN_OPTION_LANGUAGE": "en", "HOME": str(self.root)}
        self.env = patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def run_main(self, main, argv, stdin):
        out = io.StringIO()
        with patch("sys.stdin", stdin), patch("sys.stdout", out):
            self.assertEqual(main(argv), 0)
        return out.getvalue()


class ClaudeTests(GardenCase):
    def claude_stop(self) -> str:
        path = write_jsonl(self.root / "s1.jsonl", [
            prompt("p1"), reply("m1", fresh=500, written=9000),
            prompt("p2"), reply("m2", fresh=50, cached=9500, text="answer"),
        ])
        payload = {"session_id": "s1", "transcript_path": str(path), "last_assistant_message": "answer"}
        return self.run_main(hook.main, [], Pipe(json.dumps(payload)))

    def test_claude_hook_prints_both_views_and_counts_a_turn_once(self) -> None:
        out = json.loads(self.claude_stop())
        self.assertEqual(out["language"], "en")
        self.assertIn("Bonsai", out["summary"][0])
        self.assertTrue(out["full"][0].startswith("┌"))
        self.assertEqual(out["systemMessage"], "\n".join(out["summary"]))
        xp = load_state(self.data).xp
        self.claude_stop()
        self.assertEqual(load_state(self.data).xp, xp)
        self.assertEqual(load_state(self.data).turns, 1)

    def test_claude_hook_formats(self) -> None:
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_OPTION_FORMAT": "full"}):
            self.assertTrue(json.loads(self.claude_stop())["systemMessage"].startswith("┌"))
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_OPTION_FORMAT": "off"}):
            out = json.loads(self.claude_stop())
        self.assertNotIn("systemMessage", out)
        self.assertIn("summary", out)

    def test_claude_hook_never_fails(self) -> None:
        self.assertEqual(self.run_main(hook.main, [], Pipe("not json")), "")
        self.assertIn("claude-hook", (self.data / "error.log").read_text(encoding="utf-8"))

    def test_manual_runs_do_not_read_stdin(self) -> None:
        stdin = Pipe("")
        stdin.read = lambda *a: self.fail("read stdin")  # type: ignore[method-assign]
        self.assertIn("Bonsai", self.run_main(hook.main, ["--text"], stdin))
        self.assertIn("┌", self.run_main(hook.main, ["--full"], stdin))
        self.assertIn("Bonsai", self.run_main(agy.main, ["--text"], stdin))

    def test_switch(self) -> None:
        self.assertIn("locked", self.run_main(hook.main, ["--switch", "cactus"], Tty()))
        save_state(GardenState(unlocked=["bonsai", "cactus"]), self.data)
        self.assertIn("Cactus", self.run_main(agy.main, ["--switch", "cactus"], Tty()))
        self.assertEqual(load_state(self.data).species, "cactus")


class AgyTests(GardenCase):
    def transcript(self) -> Path:
        folder = self.root / ".gemini" / "antigravity-cli" / "brain" / "conv-1" / ".system_generated" / "logs"
        return write_jsonl(folder / "transcript.jsonl", [
            {"type": "USER_INPUT", "step_index": 0, "content": "hi", "created_at": "2026-10-18T10:00:00Z"},
            {"type": "PLANNER_RESPONSE", "input_tokens": 4000, "output_tokens": 20},
            {"type": "USER_INPUT", "step_index": 2, "content": "next", "created_at": "2026-10-18T10:01:00Z"},
            {"type": "PLANNER_RESPONSE", "input_tokens": 100, "cache_read_tokens": 3900, "output_tokens": 20},
            {"type": "PLANNER_RESPONSE", "input_tokens": 150, "cache_read_tokens": 4000, "output_tokens": 30},
            {"type": "USER_INPUT", "step_index": 5, "content": "cancelled"},
        ])

    def test_parse_last_answered_turn(self) -> None:
        key, turn = agy.parse_agy_turn(self.transcript())
        self.assertEqual(key, "2")
        self.assertEqual(turn.input_tokens, 250)
        self.assertEqual(turn.cache_read_tokens, 7900)
        self.assertEqual(turn.context_tokens, 4150)
        self.assertFalse(turn.fresh_session)
        self.assertEqual(agy.conversation_id(self.transcript()), "conv-1")

    def test_hook_records_once_and_allows_the_stop(self) -> None:
        payload = json.dumps({"transcriptPath": str(self.transcript())})
        self.assertEqual(json.loads(self.run_main(agy.main, [], Pipe(payload))), {"decision": "allow"})
        xp = load_state(self.data).xp
        self.assertGreater(xp, 0)
        # A manual run finds the same latest transcript and does not count it again.
        self.assertIn("┌", self.run_main(agy.main, ["--full"], Tty()))
        self.assertEqual(load_state(self.data).xp, xp)

    def test_install_hook_keeps_other_hooks(self) -> None:
        hooks = self.root / "hooks.json"
        hooks.write_text(json.dumps({"friendly-reminder": {"Stop": []}}), encoding="utf-8")
        agy.install_hook(hooks)
        data = json.loads(hooks.read_text(encoding="utf-8"))
        self.assertIn("friendly-reminder", data)
        self.assertTrue(data["virtual-garden"]["Stop"][0]["command"].endswith("virtual-garden-agy"))


if __name__ == "__main__":
    unittest.main()
