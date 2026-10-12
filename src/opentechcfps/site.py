from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from opentechcfps import countries
from opentechcfps.models import format_utc, is_past, reference_date, status

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Call for papers",
    "type": "object",
    "required": ["id", "source", "url", "name", "online", "tags", "status"],
    "properties": {
        "id": {"type": "string", "description": "Stable identifier, '<source>:<slug>'."},
        "source": {"type": "string", "description": "Where the record came from."},
        "url": {"type": "string", "format": "uri", "description": "Page to submit a talk on."},
        "name": {"type": "string"},
        "website": {"type": ["string", "null"], "format": "uri"},
        "event_start": {"type": ["string", "null"], "format": "date"},
        "event_end": {
            "type": ["string", "null"],
            "format": "date",
            "description": "Null for one-day events.",
        },
        "cfp_open": {
            "type": ["string", "null"],
            "format": "date",
            "description": "Calendar date the call opens, in the organiser's timezone.",
        },
        "cfp_close_utc": {
            "type": ["string", "null"],
            "format": "date-time",
            "description": "Exact instant the call closes, in UTC. The authoritative deadline.",
        },
        "cfp_timezone": {"type": ["string", "null"], "description": "Organiser's timezone."},
        "location": {"type": ["string", "null"], "description": "Venue and city as published."},
        "country": {
            "type": ["string", "null"],
            "description": "ISO 3166-1 alpha-2. Null when online or not recognised.",
        },
        "online": {"type": "boolean", "description": "True when no physical location is given."},
        "tags": {"type": "array", "items": {"type": "string"}},
        "perks": {
            "type": "object",
            "description": "What speakers get: travel, accommodation, fee.",
            "additionalProperties": {"type": "string"},
        },
        "summary": {"type": "string"},
        "first_seen": {"type": ["string", "null"], "format": "date-time"},
        "updated": {"type": ["string", "null"], "format": "date-time"},
        "status": {
            "enum": ["open", "upcoming", "closed", "unknown"],
            "description": "As of generated_at. Recompute from cfp_close_utc if that is stale.",
        },
    },
}


def build(
    records: dict[str, dict], out_dir: Path, static_dir: Path, base_url: str, now: datetime
) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(static_dir, out_dir)
    api = out_dir / "api"
    stamp = format_utc(now)
    base_url = base_url.rstrip("/") + "/"

    live, archive = [], defaultdict(list)
    for record in records.values():
        record = record | {"status": status(record, now)}
        if is_past(record, now.date()):
            ref = reference_date(record)
            archive[str(ref.year) if ref else "undated"].append(record | {"status": "closed"})
        else:
            live.append(record)
    live.sort(key=lambda r: (r["cfp_close_utc"] or "9999", r["name"].lower()))

    by_status = defaultdict(list)
    for record in live:
        by_status["closed" if record["status"] == "unknown" else record["status"]].append(record)
    # Slices hold only what a speaker can still act on.
    actionable = [r for r in live if r["status"] in ("open", "upcoming")]

    def write(path: str, title: str, items: list[dict], markdown: bool = True) -> None:
        _write_json(
            api / f"{path}.json", {"generated_at": stamp, "count": len(items), "cfps": items}
        )
        if markdown:
            _write_text(api / f"{path}.md", _markdown(title, items, stamp))

    write("active", "All CFPs for events that have not happened yet", live, markdown=False)
    write("open", "Open CFPs", by_status["open"])
    write("upcoming", "CFPs that have not opened yet", by_status["upcoming"])
    write("closed", "Closed CFPs for events that have not happened yet", by_status["closed"])
    online = [r for r in actionable if r["online"]]
    write("online", "Open and upcoming CFPs for online events", online)
    for year, items in archive.items():
        items.sort(key=lambda r: r["id"])
        write(f"archive/{year}", f"Past CFPs, {year}", items, markdown=False)

    tags = _slice(actionable, lambda r: r["tags"] or ["untagged"])
    for tag, items in tags.items():
        write(f"by-tag/{tag}", f"Open and upcoming CFPs tagged {tag}", items)
    by_country = _slice(actionable, lambda r: [r["country"]] if r["country"] else [])
    for code, items in by_country.items():
        name = countries.name_of(code)
        write(f"by-country/{code.lower()}", f"Open and upcoming CFPs in {name}", items)

    tag_index = [
        _index_entry(base_url, f"by-tag/{t}", items) | {"tag": t} for t, items in tags.items()
    ]
    country_index = [
        _index_entry(base_url, f"by-country/{c.lower()}", items)
        | {"country": c, "name": countries.name_of(c)}
        for c, items in by_country.items()
    ]
    _write_json(api / "tags.json", {"generated_at": stamp, "tags": tag_index})
    _write_json(api / "countries.json", {"generated_at": stamp, "countries": country_index})
    _write_json(out_dir / "schema.json", SCHEMA)
    _write_text(
        out_dir / "llms.txt",
        _llms_txt(base_url, stamp, by_status, tag_index, country_index, sorted(archive)),
    )


def _slice(items: list[dict], keys) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for item in items:
        for key in keys(item):
            groups[key].append(item)
    return dict(sorted(groups.items()))


def _index_entry(base_url: str, path: str, items: list[dict]) -> dict:
    return {
        "open": sum(r["status"] == "open" for r in items),
        "upcoming": sum(r["status"] == "upcoming" for r in items),
        "json": f"{base_url}api/{path}.json",
        "markdown": f"{base_url}api/{path}.md",
    }


def _markdown(title: str, items: list[dict], stamp: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"Generated {stamp}. {len(items)} CFPs, soonest deadline first. Times are UTC.",
        "",
        "| Name | Status | CFP closes | Event date | Where | Tags | Submit |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in items:
        close = (r["cfp_close_utc"] or "").replace("T", " ").removesuffix(":00Z")
        if r["online"]:
            where = "Online"
        else:
            where = r["location"].rsplit(",", 2)[-2:] if r["location"] else []
            where = ", ".join(part.strip() for part in where)
        cells = [
            r["name"],
            r["status"],
            close,
            r["event_start"] or "",
            where,
            ", ".join(r["tags"]),
            f"<{r['url']}>",
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines) + "\n"


def _llms_txt(base_url, stamp, by_status, tag_index, country_index, years) -> str:
    def link(path: str, label: str, note: str) -> str:
        return f"- [{label}]({base_url}{path}): {note}"

    tag_lines = [
        f"- [{t['tag']}]({t['markdown']}): {t['open']} open, {t['upcoming']} upcoming"
        for t in tag_index
    ]
    country_lines = [
        f"- [{c['name']} ({c['country']})]({c['markdown']}): "
        f"{c['open']} open, {c['upcoming']} upcoming"
        for c in country_index
    ]
    return "\n".join(
        [
            "# Open Tech CFPs",
            "",
            "> Calls for papers (calls for speakers) at technology conferences and meetups, "
            "collected from Sessionize and rebuilt every 3 hours. Free to use, no key needed.",
            "",
            f"Generated {stamp}. Right now: {len(by_status['open'])} open, "
            f"{len(by_status['upcoming'])} not yet open, {len(by_status['closed'])} closed "
            "for events still ahead.",
            "",
            "How to use this:",
            "",
            "- Every list exists as JSON (`.json`) and as a Markdown table (`.md`) at the same "
            "path. Fetch the smallest list that answers the question; filter it yourself for "
            "combinations such as a tag within a country.",
            "- `cfp_close_utc` is the exact deadline in UTC. `status` is correct as of "
            "`generated_at`; if that is more than a few hours old, compare `cfp_close_utc` with "
            "the current time yourself.",
            "- `status` is `open` (submit now), `upcoming` (call not open yet) or `closed`.",
            "- `country` is ISO 3166-1 alpha-2. Online events have `online: true` and no country.",
            "- Tags come from keyword rules over the event name and description, so they can "
            "miss. Events with no match are listed under `untagged`.",
            "- `url` is the page where a speaker submits. Send people there.",
            "- Paths are stable. New ones may be added; existing ones are not renamed.",
            "",
            "## Lists",
            "",
            link("api/open.md", "Open CFPs", "every call accepting submissions now"),
            link("api/upcoming.md", "Upcoming CFPs", "calls that have not opened yet"),
            link("api/online.md", "Online events", "open and upcoming calls with no venue"),
            link("api/closed.md", "Closed CFPs", "deadline passed, event still ahead"),
            link("api/open.json", "Open CFPs as JSON", "same list with every field"),
            link("api/active.json", "Everything current as JSON", "open, upcoming and closed"),
            "",
            "## Reference",
            "",
            link("schema.json", "Record schema", "JSON Schema for one CFP"),
            link("api/tags.json", "Tag index", "every tag with counts and URLs"),
            link("api/countries.json", "Country index", "every country with counts and URLs"),
            "",
            "## By tag",
            "",
            *tag_lines,
            "",
            "## By country",
            "",
            *country_lines,
            "",
            "## Optional",
            "",
            *[
                link(f"api/archive/{y}.json", f"Archive {y}", "past events, JSON only")
                for y in years
            ],
            "",
        ]
    )


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
