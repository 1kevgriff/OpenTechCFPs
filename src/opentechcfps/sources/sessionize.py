from __future__ import annotations

import re
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node

from opentechcfps.models import format_utc
from opentechcfps.sources.base import ParseError, RawEvent

BASE = "https://sessionize.com"
SITEMAP = f"{BASE}/sitemap/events.xml"
USER_AGENT = "OpenTechCFPs/0.1 (+https://github.com/1kevgriff/OpenTechCFPs)"

_URL = re.compile(r"<loc>https://sessionize\.com/([^/<]+)/?</loc>\s*<priority>([\d.]+)</priority>")
_DATE = re.compile(r"\b(\d{1,2} [A-Z][a-z]{2} \d{4})\b")


class Sessionize:
    name = "sessionize"

    def __init__(self, min_interval: float = 1.0, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
        )
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def discover(self) -> dict[str, float]:
        return parse_sitemap(self._get(SITEMAP).text)

    def fetch(self, slug: str) -> RawEvent | None:
        response = self._get(f"{BASE}/{slug}/")
        if response.status_code == 404:
            return None
        return parse_event(response.text, slug)

    def _get(self, url: str) -> httpx.Response:
        for attempt in range(4):
            self._wait_for_slot()
            try:
                response = self._client.get(url)
            except httpx.TransportError:
                if attempt == 3:
                    raise
            else:
                if response.status_code == 404:
                    return response
                if response.status_code != 429 and response.status_code < 500:
                    response.raise_for_status()
                    return response
                if attempt == 3:
                    response.raise_for_status()
            time.sleep(5 * 2**attempt)
        raise AssertionError("unreachable")

    def _wait_for_slot(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._min_interval
        time.sleep(max(0.0, slot - now))


def parse_sitemap(xml: str) -> dict[str, float]:
    return {slug: float(priority) for slug, priority in _URL.findall(xml)}


def parse_event(html: str, slug: str) -> RawEvent:
    tree = HTMLParser(html)
    left, right = tree.css_first("#left-column"), tree.css_first("#right-column")
    name = left.css_first("h4") if left else None
    if not name or not _text(name):
        raise ParseError(f"{slug}: no event name")

    event = RawEvent(slug=slug, url=f"{BASE}/{slug}/", name=_text(name))
    for label, value in _labelled_values(tree):
        if label in ("event starts", "event date"):
            event.event_start = event.event_start or _first_date(value)
        elif label == "event ends":
            event.event_end = _first_date(value)
        elif label == "planned future dates":
            dates = sorted(_dates(value))
            if dates:
                event.event_start, event.event_end = dates[0], dates[-1]
        elif label == "location":
            lines = [_text(span) for span in value.css("span.block")] or [_text(value)]
            event.location = ", ".join(line for line in lines if line) or None
        elif label == "website":
            link = value.css_first("a[href]")
            event.website = link.attributes["href"] if link else None
        elif label.startswith("call opens"):
            event.cfp_open = _first_date(value)

    if event.event_end == event.event_start:
        event.event_end = None

    close = tree.css_first("[data-date]")
    if close:
        # "Fri, 27 Nov 2026 22:59:00 GMT|60": the instant, then the organiser's UTC offset.
        stamp = close.attributes["data-date"].split("|")[0]
        event.cfp_close_utc = format_utc(parsedate_to_datetime(stamp).astimezone(UTC))
        zone = close.parent.parent.parent.css_first("small > strong:not([data-date])")
        event.cfp_timezone = _text(zone) if zone else None

    if right:
        for heading in right.css("h3.no-margins.font-normal"):
            value = heading.parent.css_first("div.font-bold")
            if value:
                event.perks[_text(heading).replace("event fee", "fee")] = _text(value)

    event.description = "\n".join(_descriptions(left, right))
    return event


def _labelled_values(tree: HTMLParser):
    """Sessionize renders each fact as a small navy label followed by an <h2> value."""
    for label in tree.css(".font-bold.text-navy"):
        column = label.parent
        if "col-" not in (column.attributes.get("class") or ""):
            column = column.parent
        value = column.css_first("h2") if column else None
        if value:
            yield _text(label).lower(), value


def _descriptions(*columns: Node | None):
    # Free text always follows an <hr>. The last block holds the login form, which names
    # Facebook, Google and Microsoft and would otherwise tag every open event with them.
    for column in columns:
        for rule in column.css("hr") if column else []:
            block = rule.parent
            if not block.css_first("form, button"):
                text = _text(block)
                if text:
                    yield text


def _text(node: Node) -> str:
    return re.sub(r"\s+", " ", node.text(separator=" ")).strip()


def _dates(node: Node) -> list[str]:
    return [
        datetime.strptime(match, "%d %b %Y").date().isoformat()
        for match in _DATE.findall(_text(node))
    ]


def _first_date(node: Node) -> str | None:
    return next(iter(_dates(node)), None)
