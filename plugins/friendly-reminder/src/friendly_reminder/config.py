"""Settings and environment auto-detection.

Settings are the plugin options set in ``/config`` or with
``claude plugin configure``; Claude Code exports them to the hook as
``CLAUDE_PLUGIN_OPTION_<KEY>``. ``auto`` values are resolved at run time.
"""

from __future__ import annotations

import json
import locale
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
BUNDLED_DATA = PLUGIN_ROOT / "data"

CHOICES = {
    "format": ("short", "table", "detailed", "off"),
    "language": ("auto", "en", "pt"),
    "footprint_profile": ("central", "low", "high"),
    "water_scope": ("full", "onsite"),
    "comparison": ("progressive", "random"),
}


@dataclass
class Settings:
    format: str = "short"
    language: str = "en"
    currency: str = "USD"
    exchange_rate: float = 1.0
    footprint_profile: str = "central"
    water_scope: str = "full"
    comparison: str = "progressive"


def load_settings(env: Optional[Dict[str, str]] = None) -> Settings:
    env = dict(os.environ if env is None else env)
    settings = Settings()

    def option(key: str) -> Optional[str]:
        value = env.get("CLAUDE_PLUGIN_OPTION_" + key.upper(), "").strip()
        return value or None

    for key, allowed in CHOICES.items():
        value = option(key)
        if value in allowed:
            setattr(settings, key, value)
    settings.currency = (option("currency") or "USD").upper()
    try:
        rate = float(option("exchange_rate") or 1.0)
        settings.exchange_rate = rate if rate > 0 else 1.0
    except ValueError:
        pass
    return settings


DATA_DIR_NAME = "friendly-reminder-green-ai"


def data_dir() -> Optional[Path]:
    """The plugin's persistent directory: history, optional overrides, error log.

    ``GREEN_AI_DATA`` or ``CLAUDE_PLUGIN_DATA`` when set; otherwise the folder
    Claude Code would name for this plugin, so the mod, the agy adapter and a
    manual run share one history whichever tool was installed first.
    """
    value = os.environ.get("GREEN_AI_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    return Path(value) if value else claude_config_dir() / "plugins" / "data" / DATA_DIR_NAME


def claude_config_dir() -> Path:
    custom = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(custom).expanduser() if custom else Path.home() / ".claude"


def claude_state_file() -> Path:
    custom = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(custom).expanduser() / ".claude.json") if custom else Path.home() / ".claude.json"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_language(env: Optional[Dict[str, str]] = None) -> str:
    """``pt`` or ``en`` from Claude Code's ``language`` setting, then the locale."""
    env = dict(os.environ if env is None else env)
    configured = str(_read_json(claude_config_dir() / "settings.json").get("language") or "").lower()
    if configured:
        return "pt" if configured.startswith(("pt", "portug")) else "en"
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = env.get(var, "")
        if value and value not in ("C", "POSIX"):
            return "pt" if value.lower().startswith("pt") else "en"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    return "pt" if loc.lower().startswith("pt") else "en"


PLAN_LABELS = {
    "claude_pro": "Pro",
    "claude_max": "Max",
    "claude_team": "Team",
    "claude_enterprise": "Enterprise",
}


@dataclass
class Billing:
    """How this Claude Code install pays for tokens."""

    mode: str  # "subscription", "api", "bedrock", "vertex", "foundry" or "unknown"
    plan: Optional[str] = None

    @property
    def is_subscription(self) -> bool:
        return self.mode == "subscription"

    @property
    def partner_pricing(self) -> bool:
        return self.mode in ("bedrock", "vertex")


def detect_billing(env: Optional[Dict[str, str]] = None) -> Billing:
    """Detect the billing mode without ever reading credentials.

    Only non-secret fields are inspected: provider switches and key *presence*
    in the environment, and the account's plan type in ``~/.claude.json``.
    """
    env = dict(os.environ if env is None else env)

    def truthy(name: str) -> bool:
        return env.get(name, "").strip().lower() in ("1", "true", "yes")

    for provider in ("bedrock", "vertex", "foundry"):
        if truthy(f"CLAUDE_CODE_USE_{provider.upper()}"):
            return Billing(provider)
    if env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN"):
        return Billing("api")
    if _read_json(claude_config_dir() / "settings.json").get("apiKeyHelper"):
        return Billing("api")

    account = _read_json(claude_state_file()).get("oauthAccount") or {}
    org_type = str(account.get("organizationType") or "")
    if org_type in PLAN_LABELS:
        return Billing("subscription", PLAN_LABELS[org_type])
    return Billing("unknown")
