from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from opentechcfps import site, store, update
from opentechcfps.models import is_past
from opentechcfps.sources.sessionize import Sessionize
from opentechcfps.tags import Tagger

log = logging.getLogger("opentechcfps")
DEFAULT_BASE_URL = "https://1kevgriff.github.io/OpenTechCFPs/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opentechcfps")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--tags", type=Path, default=Path("tags.yml"))
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("update", help="fetch events and update data/")
    fetch.add_argument("--all", action="store_true", help="refetch every event (backfill)")
    fetch.add_argument("--limit", type=int, help="fetch at most this many events")
    fetch.add_argument("--interval", type=float, default=1.0, help="seconds between requests")

    commands.add_parser("retag", help="re-apply tags.yml to archived events")

    build = commands.add_parser("build-site", help="write the site and API files")
    build.add_argument("--out", type=Path, default=Path("_site"))
    build.add_argument("--static", type=Path, default=Path("site"))
    build.add_argument("--base-url", default=DEFAULT_BASE_URL)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    now = datetime.now(UTC)
    source_dir = args.data / "sessionize"
    records = store.load(source_dir)

    if args.command == "update":
        stats = update.run(
            Sessionize(min_interval=args.interval),
            records,
            Tagger.from_file(args.tags),
            now,
            fetch_all=args.all,
            limit=args.limit,
            checkpoint=lambda: store.save(source_dir, records, now.date()),
        )
        store.save(source_dir, records, now.date())
        log.info("%s", stats)
        if not stats.healthy:
            log.error("too many failures; the page layout may have changed")
            return 1

    elif args.command == "retag":
        # Live events are retagged from their full description on the next update.
        tagger = Tagger.from_file(args.tags)
        for record in records.values():
            if is_past(record, now.date()):
                record["tags"] = tagger.tag(f"{record['name']}\n{record['summary']}")
        store.save(source_dir, records, now.date())

    elif args.command == "build-site":
        site.build(records, args.out, args.static, args.base_url, now)
        log.info("built %s from %d records", args.out, len(records))

    return 0
