from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime

# Fields that describe our bookkeeping rather than the event itself.
BOOKKEEPING = ("first_seen", "updated")


@dataclass
class Cfp:
    id: str
    source: str
    url: str
    name: str
    website: str | None = None
    event_start: str | None = None
    event_end: str | None = None
    cfp_open: str | None = None
    cfp_close_utc: str | None = None
    cfp_timezone: str | None = None
    location: str | None = None
    country: str | None = None
    online: bool = False
    tags: list[str] = field(default_factory=list)
    perks: dict[str, str] = field(default_factory=dict)
    summary: str = ""
    first_seen: str | None = None
    updated: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def format_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def status(record: dict, now: datetime) -> str:
    """open | upcoming | closed | unknown, derived from the CFP window."""
    close = record.get("cfp_close_utc")
    if not close:
        return "unknown"
    if now > parse_utc(close):
        return "closed"
    # cfp_open is a local calendar date, so this boundary is accurate to the day only.
    opens = record.get("cfp_open")
    if opens and now.date() < date.fromisoformat(opens):
        return "upcoming"
    return "open"


def reference_date(record: dict) -> date | None:
    """Latest date on which the record is still relevant."""
    dates = [date.fromisoformat(record[k]) for k in ("event_start", "event_end") if record.get(k)]
    if record.get("cfp_close_utc"):
        dates.append(parse_utc(record["cfp_close_utc"]).date())
    return max(dates, default=None)


def is_past(record: dict, today: date) -> bool:
    ref = reference_date(record)
    return ref is None or ref < today
