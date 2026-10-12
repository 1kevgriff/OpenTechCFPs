from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ParseError(Exception):
    pass


@dataclass
class RawEvent:
    """What a source could read from one event page, before tagging and country lookup."""

    slug: str
    url: str
    name: str
    website: str | None = None
    event_start: str | None = None
    event_end: str | None = None
    cfp_open: str | None = None
    cfp_close_utc: str | None = None
    cfp_timezone: str | None = None
    location: str | None = None
    perks: dict[str, str] = field(default_factory=dict)
    description: str = ""


class Source(Protocol):
    name: str

    def discover(self) -> dict[str, float]:
        """Every known event slug, mapped to a refresh priority (>= 0.5 means still live)."""

    def fetch(self, slug: str) -> RawEvent | None:
        """One event, or None when the page no longer exists. Raises ParseError."""
