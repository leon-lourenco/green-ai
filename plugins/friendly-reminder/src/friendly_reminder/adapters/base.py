"""Abstract base for platform adapters.

Each adapter bridges one AI coding tool (Claude Code, Antigravity/agy, …) to
the shared Friendly Reminder core (meter, history, render).  Implementing this
protocol is enough to get a working adapter; callers can type-check against it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseAdapter(ABC):
    """Contract every platform adapter must satisfy."""

    @abstractmethod
    def build_message(self, payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Compute the reminder text for the current turn.

        Returns ``None`` when there is nothing to show (no calls, format off, …).
        Must never raise: failures should be logged and return ``None``.
        """

    @abstractmethod
    def session_id(self, payload: Dict[str, Any]) -> str:
        """A stable identifier for the session/conversation."""

    @abstractmethod
    def turn_key(self, payload: Dict[str, Any]) -> str:
        """A stable identifier for the current turn within the session."""
