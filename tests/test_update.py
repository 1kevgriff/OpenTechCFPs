import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opentechcfps import site, update
from opentechcfps.sources.base import ParseError
from opentechcfps.sources.sessionize import parse_event
from opentechcfps.tags import Tagger

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
TAGGER = Tagger({"kotlin": ["kotlin"], "ai": ["AI"], "aws": ["aws"], "microsoft": ["microsoft"]})
SLUGS = ["kotlinconf-2027", "ndc-ai-dec-2026", "aws-user-group-alpharetta", "kanddinsky-2018"]


class FakeSource:
    name = "sessionize"

    def __init__(self, priorities: dict[str, float], broken: set[str] = frozenset()):
        self.priorities = priorities
        self.broken = broken
        self.fetched = []

    def discover(self):
        return self.priorities

    def fetch(self, slug):
        self.fetched.append(slug)
        if slug in self.broken:
            raise ParseError(slug)
        path = FIXTURES / f"{slug}.html"
        return parse_event(path.read_text(encoding="utf-8"), slug) if path.exists() else None


@pytest.fixture(autouse=True)
def small_sitemaps_allowed(monkeypatch):
    monkeypatch.setattr(update, "MIN_SITEMAP_URLS", 1)


def test_first_run_fetches_live_and_unknown_events():
    source = FakeSource({"kotlinconf-2027": 0.8, "ndc-ai-dec-2026": 0.5, "kanddinsky-2018": 0.2})
    records = {}
    stats = update.run(source, records, TAGGER, NOW)

    assert stats.added == 3 and stats.failed == 0
    kotlin = records["sessionize:kotlinconf-2027"]
    assert kotlin["country"] == "PL" and kotlin["online"] is False
    assert kotlin["tags"] == ["kotlin"]
    assert kotlin["first_seen"] == kotlin["updated"] == "2026-10-12T12:00:00Z"
    assert len(kotlin["summary"]) <= 301


def test_second_run_skips_known_past_events_and_leaves_unchanged_records_alone():
    priorities = {"kotlinconf-2027": 0.8, "ndc-ai-dec-2026": 0.5, "kanddinsky-2018": 0.2}
    records = {}
    update.run(FakeSource(priorities), records, TAGGER, NOW)
    before = json.dumps(records, sort_keys=True)

    source = FakeSource(priorities)
    stats = update.run(source, records, TAGGER, LATER)

    assert sorted(source.fetched) == ["kotlinconf-2027", "ndc-ai-dec-2026"]
    assert stats.added == stats.changed == 0
    assert json.dumps(records, sort_keys=True) == before


def test_changed_event_gets_a_new_updated_stamp_only():
    records = {}
    update.run(FakeSource({"kotlinconf-2027": 0.8}), records, TAGGER, NOW)
    records["sessionize:kotlinconf-2027"]["cfp_close_utc"] = "2026-11-20T22:59:00Z"

    stats = update.run(FakeSource({"kotlinconf-2027": 0.8}), records, TAGGER, LATER)

    kotlin = records["sessionize:kotlinconf-2027"]
    assert stats.changed == 1
    assert kotlin["cfp_close_utc"] == "2026-11-27T22:59:00Z"
    assert kotlin["first_seen"] == "2026-10-12T12:00:00Z"
    assert kotlin["updated"] == "2026-10-12T15:00:00Z"


def test_failed_and_vanished_pages_keep_their_stored_record():
    records = {}
    update.run(FakeSource({"kotlinconf-2027": 0.8}), records, TAGGER, NOW)
    stored = dict(records["sessionize:kotlinconf-2027"])

    stats = update.run(
        FakeSource({"kotlinconf-2027": 0.8, "deleted": 0.8}, broken={"kotlinconf-2027"}),
        records,
        TAGGER,
        LATER,
    )

    assert (stats.failed, stats.gone) == (1, 1)
    assert records == {"sessionize:kotlinconf-2027": stored}


def test_tiny_sitemap_stops_the_run(monkeypatch):
    monkeypatch.setattr(update, "MIN_SITEMAP_URLS", 5000)
    with pytest.raises(RuntimeError):
        update.run(FakeSource({"kotlinconf-2027": 0.8}), {}, TAGGER, NOW)


def test_site_build_writes_llm_endpoints(tmp_path):
    records = {}
    update.run(FakeSource(dict.fromkeys(SLUGS, 0.8)), records, TAGGER, NOW)
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    out = tmp_path / "out"

    site.build(records, out, static, "https://example.test/cfps", NOW)

    def cfps(path):
        return [r["id"] for r in json.loads((out / path).read_text(encoding="utf-8"))["cfps"]]

    assert (out / "index.html").exists()
    assert cfps("api/open.json") == ["sessionize:kotlinconf-2027"]
    assert sorted(cfps("api/closed.json")) == [
        "sessionize:aws-user-group-alpharetta",
        "sessionize:ndc-ai-dec-2026",
    ]
    assert len(cfps("api/active.json")) == 3
    assert cfps("api/by-tag/kotlin.json") == ["sessionize:kotlinconf-2027"]
    assert cfps("api/by-country/pl.json") == ["sessionize:kotlinconf-2027"]
    assert cfps("api/archive/2018.json") == ["sessionize:kanddinsky-2018"]
    # Closed calls are not worth a slice of their own.
    assert not (out / "api/by-country/no.json").exists()

    table = (out / "api/open.md").read_text(encoding="utf-8")
    assert "| KotlinConf 2027 | open | 2026-11-27 22:59 | 2027-04-21 | Kraków, Poland |" in table

    llms = (out / "llms.txt").read_text(encoding="utf-8")
    assert "https://example.test/cfps/api/open.md" in llms
    assert "[Poland (PL)](https://example.test/cfps/api/by-country/pl.md): 1 open" in llms
    assert json.loads((out / "schema.json").read_text(encoding="utf-8"))["title"]
