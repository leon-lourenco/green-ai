"""Subscription quota, read from the snapshot Claude Code caches locally.

Claude Code stores the latest rate-limit utilization it fetched under
``cachedUsageUtilization`` in ``~/.claude.json``. The field is internal and
undocumented, so everything here is best effort: any surprise yields ``None``
and the quota row is simply left out.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .models import Quota


def _has_reset(window: Dict[str, Any], now: datetime) -> bool:
    try:
        resets_at = datetime.fromisoformat(str(window.get("resets_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return resets_at.tzinfo is not None and resets_at <= now


def _pct(window: Any, now: datetime) -> Optional[float]:
    """Utilization percent, or 0 when the snapshot predates the window's reset."""
    if not isinstance(window, dict) or not isinstance(window.get("utilization"), (int, float)):
        return None
    return 0.0 if _has_reset(window, now) else float(window["utilization"])


def read_quota(state_file: Path, plan: Optional[str], now: Optional[datetime] = None) -> Optional[Quota]:
    now = now or datetime.now(timezone.utc)
    try:
        state: Dict[str, Any] = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cached = state.get("cachedUsageUtilization")
    if not isinstance(cached, dict):
        return None

    account = (state.get("oauthAccount") or {}).get("accountUuid")
    if account and cached.get("accountUuid") and cached["accountUuid"] != account:
        return None  # snapshot belongs to another login

    usage = cached.get("utilization") or {}
    quota = Quota(
        plan=plan,
        five_hour_pct=_pct(usage.get("five_hour"), now),
        seven_day_pct=_pct(usage.get("seven_day"), now),
        fetched_at_ms=cached.get("fetchedAtMs") if isinstance(cached.get("fetchedAtMs"), int) else None,
    )
    if quota.five_hour_pct is None and quota.seven_day_pct is None:
        return None
    return quota
