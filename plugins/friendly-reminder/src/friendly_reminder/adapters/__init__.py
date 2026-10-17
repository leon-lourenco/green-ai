"""Platform and agent adapters for friendly-reminder."""

from typing import TYPE_CHECKING

from .base import BaseAdapter

if TYPE_CHECKING:
    from .agy import AgyAdapter, build_agy_message, parse_agy_transcript

__all__ = ["BaseAdapter", "AgyAdapter", "build_agy_message", "parse_agy_transcript"]


def __getattr__(name: str):
    if name in ("AgyAdapter", "build_agy_message", "parse_agy_transcript"):
        from . import agy
        return getattr(agy, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
