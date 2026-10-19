"""Settings and environment auto-detection.

Settings are the plugin options set in ``/config`` or with
``claude plugin configure``; Claude Code exports them as
``CLAUDE_PLUGIN_OPTION_<KEY>``. The agy adapter reads the same variables.
``auto`` and ``current`` are resolved at run time.
"""

from __future__ import annotations

import json
import locale
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .species import SPECIES

CHOICES = {
    "format": ("short", "full", "off"),
    "species": ("current", *SPECIES),
    "language": ("auto", "en", "pt"),
}

DATA_DIR_NAME = "virtual-garden-green-ai"


@dataclass
class Settings:
    format: str = "short"
    species: str = "current"
    language: str = "auto"


def load_settings(env: Optional[Dict[str, str]] = None) -> Settings:
    env = dict(os.environ if env is None else env)
    settings = Settings()
    for key, allowed in CHOICES.items():
        value = env.get("CLAUDE_PLUGIN_OPTION_" + key.upper(), "").strip().lower()
        if value in allowed:
            setattr(settings, key, value)
    return settings


def claude_config_dir() -> Path:
    custom = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(custom).expanduser() if custom else Path.home() / ".claude"


def data_dir() -> Path:
    """Where the garden lives.

    ``VIRTUAL_GARDEN_DATA`` or ``CLAUDE_PLUGIN_DATA`` when set; otherwise the
    folder Claude Code names for this plugin, so the mod, the agy adapter and
    a manual run all tend the same garden.
    """
    value = os.environ.get("VIRTUAL_GARDEN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    return Path(value).expanduser() if value else claude_config_dir() / "plugins" / "data" / DATA_DIR_NAME


def detect_language(env: Optional[Dict[str, str]] = None) -> str:
    """``pt`` or ``en`` from Claude Code's ``language`` setting, then the locale."""
    env = dict(os.environ if env is None else env)
    try:
        configured = json.loads((claude_config_dir() / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        configured = {}
    wanted = str(configured.get("language") or "").lower() if isinstance(configured, dict) else ""
    if wanted:
        return "pt" if wanted.startswith(("pt", "portug")) else "en"
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = env.get(var, "")
        if value and value not in ("C", "POSIX"):
            return "pt" if value.lower().startswith("pt") else "en"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    return "pt" if loc.lower().startswith("pt") else "en"


def resolved_language(settings: Settings) -> str:
    return settings.language if settings.language != "auto" else detect_language()
