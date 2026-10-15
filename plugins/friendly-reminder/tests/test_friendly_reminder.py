"""Tests for Friendly Reminder. Run with: python3 -m unittest discover -s tests"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from friendly_reminder import history  # noqa: E402
from friendly_reminder.config import BUNDLED_DATA, Billing, Settings, detect_billing, load_settings  # noqa: E402
from friendly_reminder.footprint import FootprintModel  # noqa: E402
from friendly_reminder.meter import aggregate  # noqa: E402
from friendly_reminder.models import ApiCall, Footprint, Quota, Totals, Usage  # noqa: E402
from friendly_reminder.pricing import PriceBook, normalize_model  # noqa: E402
from friendly_reminder.quota import read_quota  # noqa: E402
from friendly_reminder.render import Formatter, render  # noqa: E402
from friendly_reminder.transcript import (  # noqa: E402
    parse_usage,
    read_entries,
    turn_calls,
    turn_is_flushed,
    turn_start_indexes,
)

FIXTURE = ROOT / "tests" / "fixtures" / "session.jsonl"
PRICES = PriceBook.load(BUNDLED_DATA / "pricing.json")
FOOTPRINT = FootprintModel.load(BUNDLED_DATA / "footprint.json")


def call(model: str, speed: str = "standard", **tokens: int) -> ApiCall:
    return ApiCall("m", model, Usage(**tokens), speed=speed)


class TranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = read_entries(FIXTURE)

    def test_truncated_last_line_is_ignored(self) -> None:
        self.assertTrue(all(isinstance(e, dict) for e in self.entries))

    def test_turn_starts_skip_tool_results_and_meta(self) -> None:
        starts = turn_start_indexes(self.entries)
        self.assertEqual([self.entries[i]["uuid"] for i in starts], ["p1", "p2"])

    def test_turn_calls_dedupe_and_include_recent_subagents(self) -> None:
        calls, prompt = turn_calls(FIXTURE, self.entries)
        self.assertEqual(prompt["uuid"], "p2")
        self.assertEqual(sorted(c.message_id for c in calls), ["m3", "s1"])

    def test_iterations_are_summed(self) -> None:
        calls, _ = turn_calls(FIXTURE, self.entries)
        m3 = next(c for c in calls if c.message_id == "m3")
        self.assertEqual(m3.usage, Usage(input=1007, cache_write_5m=300, cache_read=500, output=270))

    def test_legacy_usage_without_ttl_split_bills_as_5m(self) -> None:
        usage = parse_usage({"input_tokens": 1, "output_tokens": 2, "cache_creation_input_tokens": 40})
        self.assertEqual(usage, Usage(input=1, cache_write_5m=40, output=2))

    def test_flushed_detection(self) -> None:
        self.assertTrue(turn_is_flushed(self.entries, "Answer two, final."))
        cut = self.entries[: turn_start_indexes(self.entries)[-1] + 1]
        self.assertFalse(turn_is_flushed(cut, "Answer two, final."))


class PricingTests(unittest.TestCase):
    def test_normalize_provider_ids(self) -> None:
        self.assertEqual(normalize_model("us.anthropic.claude-opus-5-5-v1:0"), "claude-opus-5-5")
        self.assertEqual(normalize_model("claude-opus-4-5@20251101"), "claude-opus-4-5")
        self.assertEqual(normalize_model("claude-sonnet-5[1m]"), "claude-sonnet-5")
        self.assertEqual(normalize_model("claude-haiku-4-5-20251001"), "claude-haiku-4-5")

    def test_cost_by_token_class(self) -> None:
        c = call("claude-opus-5-5", input=10, output=100, cache_read=1000, cache_write_1h=2000)
        self.assertAlmostEqual(PRICES.cost(c), (10 * 4 + 100 * 20 + 1000 * 0.2 + 2000 * 8) / 1e6)

    def test_cache_write_5m_multiplier(self) -> None:
        self.assertAlmostEqual(PRICES.cost(call("claude-sonnet-5-5", cache_write_5m=1_000_000)), 2.5)

    def test_haiku_long_context_tier(self) -> None:
        short = PRICES.cost(call("claude-haiku-5-5", input=100_000, output=1_000_000))
        long = PRICES.cost(call("claude-haiku-5-5", input=100_001, output=1_000_000))
        self.assertAlmostEqual(short, 0.01 + 0.5)
        self.assertAlmostEqual(long, 100_001 * 0.5 / 1e6 + 2.5)

    def test_fast_mode(self) -> None:
        self.assertAlmostEqual(PRICES.cost(call("claude-opus-5-5", "fast", output=1_000_000)), 40.0)

    def test_unknown_model(self) -> None:
        self.assertIsNone(PRICES.cost(call("gpt-imaginary", output=10)))

    def test_override_file_adds_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            override = Path(tmp) / "pricing.json"
            override.write_text(json.dumps({"models": {"claude-new-9": {"input": 1, "output": 2}}}))
            book = PriceBook.load(BUNDLED_DATA / "pricing.json", override)
            self.assertAlmostEqual(book.cost(call("claude-new-9", output=1_000_000)), 2.0)
            self.assertTrue(book.knows("claude-opus-5-5"))


class FootprintTests(unittest.TestCase):
    def test_central_estimate_arithmetic(self) -> None:
        fp = FOOTPRINT.estimate(Usage(output=1000), "central", "full")
        self.assertAlmostEqual(fp.wh, 0.5 * 1.12)
        self.assertAlmostEqual(fp.water_ml, 0.5 * 1.12 * (0.5 + 3.1))

    def test_onsite_scope_is_smaller(self) -> None:
        usage = Usage(output=1000, cache_read=10_000)
        self.assertLess(FOOTPRINT.estimate(usage, water_scope="onsite").water_ml, FOOTPRINT.estimate(usage).water_ml)

    def test_profiles_are_ordered(self) -> None:
        usage = Usage(input=100, cache_write_1h=5000, cache_read=50_000, output=2000)
        low, mid, high = (FOOTPRINT.estimate(usage, p).wh for p in ("low", "central", "high"))
        self.assertLess(low, mid)
        self.assertLess(mid, high)


class RenderTests(unittest.TestCase):
    def setUp(self) -> None:
        calls, _ = turn_calls(FIXTURE, read_entries(FIXTURE))
        self.turn = aggregate(calls, PRICES, FOOTPRINT)
        self.month = Totals(usage=Usage(output=2_000_000), cost_usd=12.3, footprint=Footprint(900.0, 2300.0), turns=40)

    def text(self, settings: Settings = Settings(format="table"), lang: str = "pt", **kw) -> str:
        return render(self.turn, 2, settings, lang, kw.pop("billing", Billing("api")), **kw)

    def test_turn_totals(self) -> None:
        self.assertEqual(self.turn.usage.total, 4477)
        self.assertAlmostEqual(self.turn.cost_usd, 0.005964)

    def test_water_leads_the_message(self) -> None:
        lines = self.text().splitlines()
        self.assertTrue(lines[0].startswith("💧 Friendly Reminder · turno 2"))
        self.assertTrue(lines[1].startswith("Esta resposta consumiu ≈ "))
        self.assertIn("de um copo", lines[1])
        first_row = next(line for line in lines if line.startswith("│ ") and "Turno" not in line)
        self.assertIn("Água", first_row)

    def test_history_line_and_month_column(self) -> None:
        text = self.text(today=self.month, month=self.month)
        self.assertIn("Hoje: ≈ 2,30 L (≈ 9,2 copos) · Mês: ≈ 2,30 L (≈ 9,2 copos)", text)
        self.assertIn("Mês", text.splitlines()[4])
        self.assertIn("US$ 12,30", text)

    def test_without_history_there_is_no_month_column(self) -> None:
        self.assertNotIn("Mês", self.text())

    def test_glass_wording(self) -> None:
        f = Formatter(Settings(), "en")
        self.assertEqual(f.glasses(1), "under 1% of a glass")
        self.assertEqual(f.glasses(50), "20% of a glass")
        self.assertEqual(f.glasses(260), "≈ 1 glass")
        self.assertEqual(f.glasses(5000), "≈ 20 glasses")

    def test_currency_conversion(self) -> None:
        self.assertIn("R$ 0,0298", self.text(Settings(format="table", currency="BRL", exchange_rate=5.0)))

    def test_short_is_the_default_two_lines_with_water_first(self) -> None:
        self.assertEqual(Settings().format, "short")
        quota = Quota(plan="Pro", five_hour_pct=38, seven_day_pct=21)
        text = self.text(Settings(), "pt", today=self.month, month=self.month,
                         billing=Billing("subscription", "Pro"), quota=quota, flushed=False)
        first, second = text.splitlines()  # no "partial" warning line
        self.assertTrue(first.startswith("💧 "))
        self.assertIn("de água nesta resposta", first)
        self.assertIn("mês 2,3 L", first)
        self.assertTrue(second.startswith("⚡ "))
        self.assertIn("4,5 mil tokens", second)
        self.assertNotIn("cota", second)  # quota stays hidden below 50%

    def test_short_shows_quota_once_it_matters(self) -> None:
        quota = Quota(plan="Pro", five_hour_pct=12, seven_day_pct=81)
        text = self.text(Settings(), "en", billing=Billing("subscription", "Pro"), quota=quota)
        self.assertIn("Pro quota: 5h 12%, week 81%", text)

    def test_compact_numbers(self) -> None:
        f = Formatter(Settings(), "pt")
        self.assertEqual(f.compact_water(12.34), "12 mL")
        self.assertEqual(f.compact_water(2.01), "2 mL")
        self.assertEqual(f.compact_water(1420), "1,4 L")
        self.assertEqual(f.compact_water(18_600), "19 L")
        self.assertEqual(f.compact_energy(3.42), "3,4 Wh")
        self.assertEqual(f.compact_tokens(326_353), "326 mil")
        self.assertEqual(f.compact_tokens(2_064_412), "2,1 mi")
        self.assertEqual(f.compact_money(0.201), "US$ 0,20")
        self.assertEqual(f.compact_money(0.001), "menos de US$ 0,01")
        self.assertEqual(Formatter(Settings(), "en").compact_tokens(326_353), "326k")

    def test_detailed_adds_breakdown_and_range(self) -> None:
        text = self.text(Settings(format="detailed"))
        self.assertIn("Cache (leitura)", text)
        self.assertIn("Água: ", text)
        self.assertIn("Copo = 250 mL", text)

    def test_off_renders_nothing(self) -> None:
        self.assertIsNone(self.text(Settings(format="off")))

    def test_unpriced_models_are_flagged(self) -> None:
        turn = aggregate([call("mystery-model", output=5)], PRICES, FOOTPRINT)
        text = render(turn, 1, Settings(format="table"), "en", Billing("api"))
        self.assertIn("$0.00*", text)
        self.assertIn("no price for: mystery-model", text)


class ConfigTests(unittest.TestCase):
    def test_options_and_invalid_values(self) -> None:
        s = load_settings({"CLAUDE_PLUGIN_OPTION_FORMAT": "detailed", "CLAUDE_PLUGIN_OPTION_CURRENCY": "brl"})
        self.assertEqual((s.format, s.currency), ("detailed", "BRL"))
        s = load_settings({"CLAUDE_PLUGIN_OPTION_FORMAT": "fancy", "CLAUDE_PLUGIN_OPTION_EXCHANGE_RATE": "x"})
        self.assertEqual((s.format, s.exchange_rate), ("short", 1.0))

    def test_billing_detection_never_needs_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".claude.json").write_text(json.dumps({"oauthAccount": {"organizationType": "claude_max"}}))
            old = os.environ.get("CLAUDE_CONFIG_DIR")
            os.environ["CLAUDE_CONFIG_DIR"] = tmp
            try:
                self.assertEqual(detect_billing({}), Billing("subscription", "Max"))
                self.assertEqual(detect_billing({"ANTHROPIC_API_KEY": "x"}).mode, "api")
                self.assertEqual(detect_billing({"CLAUDE_CODE_USE_BEDROCK": "1"}).mode, "bedrock")
            finally:
                if old is None:
                    os.environ.pop("CLAUDE_CONFIG_DIR", None)
                else:
                    os.environ["CLAUDE_CONFIG_DIR"] = old


class QuotaTests(unittest.TestCase):
    def write(self, tmp: str, state: dict) -> Path:
        path = Path(tmp, ".claude.json")
        path.write_text(json.dumps(state))
        return path

    def test_reads_cached_utilization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {
                "oauthAccount": {"accountUuid": "a"},
                "cachedUsageUtilization": {
                    "accountUuid": "a",
                    "fetchedAtMs": 1,
                    "utilization": {"five_hour": {"utilization": 40}, "seven_day": {"utilization": 12.5}},
                },
            })
            q = read_quota(path, "Pro")
            self.assertEqual((q.five_hour_pct, q.seven_day_pct, q.plan), (40.0, 12.5, "Pro"))

    def test_window_that_already_reset_reads_as_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"cachedUsageUtilization": {"utilization": {
                "five_hour": {"utilization": 92, "resets_at": "2026-10-15T03:10:00+00:00"},
                "seven_day": {"utilization": 49, "resets_at": "2026-10-18T06:00:00+00:00"},
            }}})
            q = read_quota(path, "Pro", datetime(2026, 10, 15, 4, 0, tzinfo=timezone.utc))
            self.assertEqual((q.five_hour_pct, q.seven_day_pct), (0.0, 49.0))

    def test_other_account_or_missing_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {
                "oauthAccount": {"accountUuid": "a"},
                "cachedUsageUtilization": {"accountUuid": "b", "utilization": {"five_hour": {"utilization": 1}}},
            })
            self.assertIsNone(read_quota(path, "Pro"))
            self.assertIsNone(read_quota(Path(tmp, "missing.json"), "Pro"))


class HistoryTests(unittest.TestCase):
    def test_last_record_per_turn_wins_and_days_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            day1 = datetime(2026, 10, 14, 12, 0).astimezone()
            day2 = datetime(2026, 10, 15, 9, 0).astimezone()
            small = Totals(usage=Usage(output=10), cost_usd=1.0, footprint=Footprint(1.0, 10.0))
            big = Totals(usage=Usage(output=30), cost_usd=3.0, footprint=Footprint(3.0, 30.0))
            history.record(root, "s", "t1", small, day1)
            history.record(root, "s", "t1", big, day1)  # same turn recorded again
            history.record(root, "s", "t2", small, day2)
            today, month = history.summary(root, day2)
            self.assertEqual((month.turns, month.usage.output, month.footprint.water_ml), (2, 40, 40.0))
            self.assertEqual((today.turns, today.footprint.water_ml), (1, 10.0))


class HookEndToEndTests(unittest.TestCase):
    script = ROOT / "scripts" / "friendly-reminder"

    def run_hook(self, payload: dict, tmp: str, **env: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "CLAUDE_PLUGIN_DATA": tmp, "CLAUDE_PLUGIN_OPTION_LANGUAGE": "en", **env}
        return subprocess.run(
            [sys.executable, str(self.script)],
            input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30,
        )

    def payload(self) -> dict:
        return {"session_id": "abc", "transcript_path": str(FIXTURE), "last_assistant_message": "Answer two, final."}

    def test_emits_system_message_and_records_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_hook(self.payload(), tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            message = json.loads(result.stdout)["systemMessage"]
            self.assertIn("of water in this response", message)
            self.assertIn("4.5k tokens", message)
            self.assertIn("today 2 mL", message)
            self.assertTrue(list(Path(tmp, "history").glob("*.jsonl")))

    def test_off_is_silent_but_still_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_hook(self.payload(), tmp, CLAUDE_PLUGIN_OPTION_FORMAT="off")
            self.assertEqual((result.returncode, result.stdout), (0, ""))
            self.assertTrue(list(Path(tmp, "history").glob("*.jsonl")))

    def test_failures_stay_silent_and_are_logged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pricing.json").write_text("{not json")
            result = self.run_hook({"transcript_path": str(FIXTURE)}, tmp)
            self.assertEqual((result.returncode, result.stdout), (0, ""))
            self.assertIn("Traceback", Path(tmp, "error.log").read_text())


if __name__ == "__main__":
    unittest.main()
