from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from opentechcfps import countries
from opentechcfps.models import BOOKKEEPING, Cfp, format_utc, is_past
from opentechcfps.sources.base import RawEvent, Source
from opentechcfps.tags import Tagger

log = logging.getLogger(__name__)

MIN_SITEMAP_URLS = 5000
MAX_FAILURE_RATE = 0.05
SUMMARY_LENGTH = 300
CHECKPOINT_EVERY = 500


@dataclass
class Stats:
    attempted: int = 0
    added: int = 0
    changed: int = 0
    gone: int = 0
    failed: int = 0

    @property
    def healthy(self) -> bool:
        return self.attempted < 20 or self.failed / self.attempted <= MAX_FAILURE_RATE


def build_record(raw: RawEvent, source: str, tagger: Tagger) -> dict:
    summary = raw.description[:SUMMARY_LENGTH]
    if len(raw.description) > SUMMARY_LENGTH:
        summary = re.sub(r"\s+\S*$", "", summary) + "…"
    return Cfp(
        id=f"{source}:{raw.slug}",
        source=source,
        url=raw.url,
        name=raw.name,
        website=raw.website,
        event_start=raw.event_start,
        event_end=raw.event_end,
        cfp_open=raw.cfp_open,
        cfp_close_utc=raw.cfp_close_utc,
        cfp_timezone=raw.cfp_timezone,
        location=raw.location,
        country=countries.resolve(raw.location),
        online=countries.is_online(raw.location),
        tags=tagger.tag(f"{raw.name}\n{raw.description}"),
        perks=raw.perks,
        summary=summary,
    ).to_dict()


def select(
    sitemap: dict[str, float], records: dict[str, dict], source: str, now: datetime, fetch_all: bool
) -> list[str]:
    """Slugs to fetch, most live first."""
    prefix = f"{source}:"
    if fetch_all:
        chosen = set(sitemap)
    else:
        chosen = {slug for slug, priority in sitemap.items() if priority >= 0.5}
        chosen |= {slug for slug in sitemap if prefix + slug not in records}
        # Stored events still ahead of us get checked even after the sitemap demotes them,
        # so their final state is captured before they move to the archive.
        chosen |= {
            key[len(prefix) :]
            for key, record in records.items()
            if key.startswith(prefix) and not is_past(record, now.date())
        }
    return sorted(chosen, key=lambda slug: (-sitemap.get(slug, 0.0), slug))


def run(
    source: Source,
    records: dict[str, dict],
    tagger: Tagger,
    now: datetime,
    *,
    fetch_all: bool = False,
    limit: int | None = None,
    workers: int = 2,
    checkpoint: Callable[[], None] = lambda: None,
) -> Stats:
    sitemap = source.discover()
    if len(sitemap) < MIN_SITEMAP_URLS:
        raise RuntimeError(f"sitemap returned only {len(sitemap)} events; refusing to continue")

    slugs = select(sitemap, records, source.name, now, fetch_all)[:limit]
    log.info("%d events in sitemap, fetching %d", len(sitemap), len(slugs))

    def fetch(slug: str):
        try:
            return slug, source.fetch(slug), None
        except Exception as error:  # one bad page must not sink the run
            return slug, None, error

    stats = Stats()
    stamp = format_utc(now)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for slug, raw, error in pool.map(fetch, slugs):
            stats.attempted += 1
            if error:
                stats.failed += 1
                log.warning("%s: %s", slug, error)
            elif raw is None:
                stats.gone += 1
            else:
                _merge(records, build_record(raw, source.name, tagger), stamp, stats)
            if stats.attempted % CHECKPOINT_EVERY == 0:
                log.info("%d/%d fetched", stats.attempted, len(slugs))
                checkpoint()
    return stats


def _merge(records: dict[str, dict], new: dict, stamp: str, stats: Stats) -> None:
    old = records.get(new["id"])
    if old is None:
        stats.added += 1
        records[new["id"]] = new | {"first_seen": stamp, "updated": stamp}
        return
    if old.get("cfp_close_utc") and not new["cfp_close_utc"]:
        # A page that suddenly has no deadline is far more likely a markup change than news.
        stats.failed += 1
        log.warning("%s: lost its CFP close date; keeping the stored record", new["id"])
        return
    new["first_seen"] = old.get("first_seen")
    new["updated"] = old.get("updated")
    if any(old.get(k) != v for k, v in new.items() if k not in BOOKKEEPING):
        stats.changed += 1
        new["updated"] = stamp
    records[new["id"]] = new
