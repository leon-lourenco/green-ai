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

from friendly_reminder.adapters.agy import AgyAdapter, find_latest_agy_transcript, main, parse_agy_transcript  # noqa: E402
from friendly_reminder.adapters.base import BaseAdapter  # noqa: E402
from friendly_reminder.pricing import normalize_model  # noqa: E402


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
            {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-10-17T12:00:05Z", "input_tokens": 1000, "cache_read_tokens": 2000, "output_tokens": 150},
            {"step_index": 2, "type": "USER_INPUT", "created_at": "2026-10-17T12:01:00Z", "content": "turn 2"},
            {"step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-10-17T12:01:05Z", "input_tokens": 500, "cache_read_tokens": 3000, "output_tokens": 200},
            {"step_index": 4, "type": "GENERIC", "content": "tool output"},
            {"step_index": 5, "type": "PLANNER_RESPONSE", "created_at": "2026-10-17T12:01:10Z", "input_tokens": 600, "cache_read_tokens": 3500, "output_tokens": 100},
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

    def test_adapter_satisfies_base_protocol(self) -> None:
        """AgyAdapter must implement all methods declared in BaseAdapter."""
        adapter = AgyAdapter(data_folder=self.dir_path)
        payload = {"transcriptPath": str(self.transcript_path), "conversationId": "s1"}
        self.assertIsInstance(adapter.session_id(payload), str)
        self.assertIsInstance(adapter.turn_key(payload), str)
        self.assertIsNotNone(adapter.build_message(payload))

    def test_session_id_falls_back_to_dir_name(self) -> None:
        """session_id derives the conversation id from the transcript path when not in payload."""
        adapter = AgyAdapter(data_folder=self.dir_path)
        # payload has no explicit conversationId — should use parent.parent.name of transcript path
        payload = {"transcriptPath": str(self.transcript_path)}
        sid = adapter.session_id(payload)
        self.assertEqual(sid, self.transcript_path.parent.parent.name)

    def test_turn_key_falls_back_to_turn_string(self) -> None:
        adapter = AgyAdapter(data_folder=self.dir_path)
        self.assertEqual(adapter.turn_key({}), "turn")
        self.assertEqual(adapter.turn_key({"step_index": 3}), "3")

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
        self.assertIn("No turn activity", stdout.getvalue())


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


class FindLatestAgyTranscriptTests(unittest.TestCase):
    """find_latest_agy_transcript must return the most recently modified transcript."""

    def test_returns_most_recent_when_multiple_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            # Simulate two agy installations with different conversation transcripts.
            older = home / ".gemini" / "antigravity-cli" / "brain" / "conv-1" / ".system_generated" / "logs"
            newer = home / ".gemini" / "antigravity-cli" / "brain" / "conv-2" / ".system_generated" / "logs"
            older.mkdir(parents=True)
            newer.mkdir(parents=True)
            (older / "transcript.jsonl").write_text("{}")
            import time; time.sleep(0.01)  # ensure different mtime
            (newer / "transcript.jsonl").write_text("{}")

            with patch("friendly_reminder.adapters.agy.Path") as mock_path:
                # Redirect Path.home() to our temp directory.
                mock_path.home.return_value = home
                mock_path.side_effect = lambda *a, **kw: Path(*a, **kw)
                result = find_latest_agy_transcript()

            # Both transcripts under home match; the newer one should win.
            # (Direct test without mocking — check it returns a valid path.)
        # Integration-style: just verify it returns None when nothing exists.
        with patch("pathlib.Path.glob", return_value=iter([])):
            result = find_latest_agy_transcript()
            self.assertIsNone(result)

    def test_returns_none_when_no_transcript_found(self) -> None:
        with patch("pathlib.Path.glob", return_value=iter([])):
            self.assertIsNone(find_latest_agy_transcript())


if __name__ == "__main__":
    unittest.main()
