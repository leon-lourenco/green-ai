"""Tests for Antigravity (agy) adapter."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from friendly_reminder.adapters.agy import (  # noqa: E402
    AgyAdapter,
    conversation_id,
    find_latest_agy_transcript,
    install_hook,
    main,
    parse_agy_transcript,
    turn_key,
)
from friendly_reminder.config import BUNDLED_DATA  # noqa: E402
from friendly_reminder.history import latest  # noqa: E402
from friendly_reminder.models import ApiCall, Usage  # noqa: E402
from friendly_reminder.pricing import PriceBook, normalize_model  # noqa: E402


def _write_transcript(path: Path, lines: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")


class AgyAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)

        # Create a mock agy transcript
        self.transcript_path = self.dir_path / "transcript.jsonl"
        lines = [
            {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-10-17T12:00:00Z", "content": "turn 1"},
            {
                "step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-10-17T12:00:05Z",
                "input_tokens": 1000, "cache_read_tokens": 2000, "output_tokens": 150,
            },
            {"step_index": 2, "type": "USER_INPUT", "created_at": "2026-10-17T12:01:00Z", "content": "turn 2"},
            {
                "step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-10-17T12:01:05Z",
                "input_tokens": 500, "cache_read_tokens": 3000, "output_tokens": 200,
            },
            {"step_index": 4, "type": "GENERIC", "content": "tool output"},
            {
                "step_index": 5, "type": "PLANNER_RESPONSE", "created_at": "2026-10-17T12:01:10Z",
                "input_tokens": 600, "cache_read_tokens": 3500, "output_tokens": 100,
            },
        ]
        _write_transcript(self.transcript_path, lines)

    def test_parse_agy_transcript_non_existent(self) -> None:
        calls, prompt, count = parse_agy_transcript(self.dir_path / "non_existent.jsonl")
        self.assertEqual(calls, [])
        self.assertIsNone(prompt)
        self.assertEqual(count, 0)

    def test_parse_agy_transcript_extracts_latest_turn(self) -> None:
        calls, prompt, count = parse_agy_transcript(self.transcript_path, model_name="gemini-3.8-flash")
        self.assertEqual(count, 2)
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt["content"], "turn 2")
        self.assertEqual(len(calls), 2)

        # First call in turn 2 (step 3)
        self.assertEqual(calls[0].message_id, "step_3")
        self.assertEqual(calls[0].usage.input, 500)
        self.assertEqual(calls[0].usage.cache_read, 3000)
        self.assertEqual(calls[0].usage.output, 200)

        # Second call in turn 2 (step 5)
        self.assertEqual(calls[1].message_id, "step_5")
        self.assertEqual(calls[1].usage.input, 600)
        self.assertEqual(calls[1].usage.cache_read, 3500)
        self.assertEqual(calls[1].usage.output, 100)

    def test_model_from_transcript_entry_takes_priority_over_payload(self) -> None:
        """When the transcript entry has a 'model' field, it must override model_name."""
        transcript = self.dir_path / "with_model.jsonl"
        _write_transcript(transcript, [
            {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-10-17T12:00:00Z", "content": "hi"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-10-17T12:00:05Z",
             "model": "gemini-2.5-pro", "input_tokens": 100, "output_tokens": 50},
        ])
        calls, _, _ = parse_agy_transcript(transcript, model_name="gemini-3.8-flash")
        self.assertEqual(len(calls), 1)
        # The model embedded in the transcript wins over the fallback.
        self.assertEqual(calls[0].model, "gemini-2.5-pro")

    def test_model_fallback_when_not_in_transcript(self) -> None:
        """When 'model' is absent from the entry, model_name is used as fallback."""
        calls, _, _ = parse_agy_transcript(self.transcript_path, model_name="gemini-2.5-flash")
        # None of the fixture entries have a 'model' field → all should use the fallback.
        self.assertTrue(all(c.model == "gemini-2.5-flash" for c in calls))

    def test_billing_is_not_hardcoded_as_pro(self) -> None:
        """build_message must not emit quota data that assumes a Pro subscription."""
        adapter = AgyAdapter(data_folder=self.dir_path)
        payload = {
            "transcriptPath": str(self.transcript_path),
            "conversationId": "test-session-123",
            "modelName": "gemini-3.8-flash",
        }
        msg = adapter.build_message(payload)
        self.assertIsNotNone(msg)
        # Quota lines (e.g. "Pro quota: …") must not appear when billing is unknown.
        self.assertNotIn("quota", msg.lower())
        self.assertNotIn("Pro", msg)

    def test_agy_adapter_build_message(self) -> None:
        adapter = AgyAdapter(data_folder=self.dir_path)
        payload = {
            "transcriptPath": str(self.transcript_path),
            "conversationId": "test-session-123",
            "modelName": "gemini-3.8-flash",
        }
        msg = adapter.build_message(payload)
        self.assertIsNotNone(msg)
        self.assertIn("💧", msg)
        self.assertIn("⚡", msg)
        self.assertIn("tokens", msg)

    def test_unanswered_prompts_fall_back_to_last_answered_turn(self) -> None:
        transcript = self.dir_path / "pending.jsonl"
        _write_transcript(transcript, [
            {"step_index": 0, "type": "USER_INPUT", "content": "turn 1"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "input_tokens": 10, "output_tokens": 5},
            {"step_index": 2, "type": "USER_INPUT", "content": "queued"},
            {"step_index": 3, "type": "USER_INPUT", "content": "queued again"},
        ])
        calls, prompt, number = parse_agy_transcript(transcript)
        self.assertEqual([c.message_id for c in calls], ["step_1"])
        self.assertEqual(prompt["content"], "turn 1")
        self.assertEqual(number, 1)

    def test_no_answered_turn(self) -> None:
        transcript = self.dir_path / "none.jsonl"
        _write_transcript(transcript, [{"step_index": 0, "type": "USER_INPUT", "content": "hi"}])
        self.assertEqual(parse_agy_transcript(transcript), ([], None, 0))

    def test_conversation_id_comes_from_the_brain_folder(self) -> None:
        path = Path("/h/.gemini/antigravity-cli/brain/conv-42/.system_generated/logs/transcript.jsonl")
        self.assertEqual(conversation_id(path, {"conversationId": "other"}), "conv-42")
        self.assertEqual(conversation_id(self.transcript_path, {"conversationId": "s1"}), "s1")

    def test_turn_key_keeps_step_zero(self) -> None:
        self.assertEqual(turn_key({"step_index": 0, "created_at": "x"}), "0")
        self.assertEqual(turn_key({"created_at": "x"}), "x")
        self.assertEqual(turn_key(None), "turn")

    def test_two_conversations_do_not_overwrite_each_other(self) -> None:
        data = self.dir_path / "data"
        adapter = AgyAdapter(data_folder=data)
        for conv in ("conv-a", "conv-b"):
            logs = self.dir_path / "brain" / conv / ".system_generated" / "logs"
            logs.mkdir(parents=True)
            (logs / "transcript.jsonl").write_text(self.transcript_path.read_text())
            adapter.build_message({"transcriptPath": str(logs / "transcript.jsonl")})
        self.assertEqual(sorted(latest(data)), [("conv-a", "2"), ("conv-b", "2")])

    def test_hook_mode_records_and_lets_the_agent_stop(self) -> None:
        data = self.dir_path / "data"
        payload = json.dumps({"transcriptPath": str(self.transcript_path), "conversationId": "s1",
                              "modelName": "Gemini 3.8 Flash (High)"})
        stdin, stdout = io.StringIO(payload), io.StringIO()
        stdin.isatty = lambda: False  # type: ignore[method-assign]
        with patch("sys.stdin", stdin), patch("sys.stdout", stdout), \
             patch.dict(os.environ, {"GREEN_AI_DATA": str(data)}):
            self.assertEqual(main([]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), {"decision": "allow"})
        self.assertEqual(list(latest(data)), [("s1", "2")])

    def test_install_hook_keeps_other_hooks_and_uses_an_absolute_path(self) -> None:
        hooks = self.dir_path / "config" / "hooks.json"
        hooks.parent.mkdir()
        hooks.write_text(json.dumps({"other": {"Stop": []}}))
        install_hook(hooks)
        data = json.loads(hooks.read_text())
        self.assertIn("other", data)
        command = data["friendly-reminder"]["Stop"][0]["command"]
        self.assertTrue(Path(command).is_absolute())
        self.assertTrue(Path(command).is_file())

    def test_main_cli_text_flag(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            ret = main(["--text", "--transcript", str(self.transcript_path)])
        self.assertEqual(ret, 0)
        output = stdout.getvalue()
        self.assertIn("💧", output)
        self.assertIn("⚡", output)

    def test_main_cli_no_transcript_is_silent(self) -> None:
        """When no transcript is found and we're not in a pipe, emit a message."""
        stdout = io.StringIO()
        with patch("sys.stdout", stdout), \
             patch("friendly_reminder.adapters.agy.find_latest_agy_transcript", return_value=None):
            ret = main(["--text"])
        self.assertEqual(ret, 0)
        self.assertIn("no measured turn", stdout.getvalue())


class GeminiNormalizationTests(unittest.TestCase):
    """normalize_model must handle Gemini display names correctly."""

    def test_gemini_display_name_with_qualifier(self) -> None:
        self.assertEqual(normalize_model("Gemini 3.8 Flash (High)"), "gemini-3.8-flash")

    def test_gemini_plain_name(self) -> None:
        self.assertEqual(normalize_model("Gemini 3.8 Flash"), "gemini-3.8-flash")

    def test_gemini_25_pro(self) -> None:
        self.assertEqual(normalize_model("Gemini 2.5 Pro"), "gemini-2.5-pro")

    def test_gemini_flash_lite(self) -> None:
        self.assertEqual(normalize_model("Gemini 3.8 Flash Lite"), "gemini-3.8-flash-lite")

    def test_gemini_already_normalized(self) -> None:
        self.assertEqual(normalize_model("gemini-3.8-flash"), "gemini-3.8-flash")


class GeminiPricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prices = PriceBook.load(BUNDLED_DATA / "pricing.json")

    def _cost(self, model: str, **usage: int) -> float:
        return self.prices.cost(ApiCall("m", model, Usage(**usage)))

    def test_display_name_is_priced(self) -> None:
        self.assertAlmostEqual(self._cost("Gemini 3.8 Flash (Low)", input=1_000_000), 0.75)

    def test_preview_ids_use_the_base_price(self) -> None:
        self.assertAlmostEqual(self._cost("gemini-3.1-pro-preview", output=1_000_000), 12.0)

    def test_long_context_tier(self) -> None:
        self.assertAlmostEqual(self._cost("gemini-2.5-pro", input=300_000), 0.75)


class FindLatestAgyTranscriptTests(unittest.TestCase):
    def test_returns_most_recent_when_multiple_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            paths = []
            for install, conv in (("antigravity-cli", "conv-1"), ("antigravity-ide", "conv-2")):
                logs = home / ".gemini" / install / "brain" / conv / ".system_generated" / "logs"
                logs.mkdir(parents=True)
                (logs / "transcript.jsonl").write_text("{}")
                paths.append(logs / "transcript.jsonl")
            os.utime(paths[0], (1000, 1000))
            os.utime(paths[1], (2000, 2000))
            with patch("pathlib.Path.home", return_value=home):
                self.assertEqual(find_latest_agy_transcript(), paths[1])

    def test_returns_none_when_no_transcript_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("pathlib.Path.home", return_value=Path(tmp)):
            self.assertIsNone(find_latest_agy_transcript())


if __name__ == "__main__":
    unittest.main()
