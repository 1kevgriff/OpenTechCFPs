from pathlib import Path

import pytest

from opentechcfps.sources.base import ParseError
from opentechcfps.sources.sessionize import parse_event, parse_sitemap

FIXTURES = Path(__file__).parent / "fixtures"


def load(slug: str):
    return parse_event((FIXTURES / f"{slug}.html").read_text(encoding="utf-8"), slug)


def test_sitemap_keeps_slug_case_and_priority():
    sitemap = parse_sitemap((FIXTURES / "sitemap.xml").read_text(encoding="utf-8"))
    assert sitemap == {"kotlinconf-2027": 0.8, "ndc-ai-dec-2026": 0.5, "JUC-IL-2018": 0.2}


def test_in_person_event_with_open_call():
    event = load("kotlinconf-2027")
    assert event.name == "KotlinConf 2027"
    assert event.url == "https://sessionize.com/kotlinconf-2027/"
    assert event.website == "https://kotlinconf.com"
    assert (event.event_start, event.event_end) == ("2027-04-21", "2027-04-23")
    assert event.cfp_open == "2026-10-01"
    assert event.cfp_close_utc == "2026-11-27T22:59:00Z"
    assert event.cfp_timezone == "W. Europe Standard Time (UTC+01:00)"
    assert event.location == "ICE Krakow Congress Centre, Kraków, Poland"
    assert event.perks == {
        "travel": "expenses covered",
        "accommodation": "expenses covered",
        "fee": "free for speakers",
    }
    assert event.description.startswith("KotlinConf is the official Kotlin Community conference")
    assert "Submit your proposal by 27.11" in event.description


def test_login_form_is_not_part_of_the_description():
    assert "Facebook" not in load("kotlinconf-2027").description


def test_online_group_with_one_planned_date():
    event = load("datawit-2027")
    assert event.name == "Data Platform Women in Technology Virtual Group 2027"
    assert (event.event_start, event.event_end) == ("2027-01-12", None)
    assert event.location is None
    assert event.website is None
    assert event.cfp_close_utc == "2027-09-02T03:59:00Z"
    assert event.perks == {}


def test_single_line_location():
    event = load("aws-user-group-alpharetta")
    assert event.location == "Alpharetta, Georgia, United States"
    assert event.event_start == "2026-10-13"
    assert event.cfp_close_utc == "2026-09-26T03:59:00Z"


def test_closed_call_for_upcoming_event():
    event = load("ndc-ai-dec-2026")
    assert (event.event_start, event.event_end) == ("2026-12-07", "2026-12-09")
    assert event.location == "Rebel Oslo, Oslo, Norway"
    assert event.cfp_close_utc == "2026-10-04T21:59:00Z"
    assert event.cfp_timezone == "W. Europe Daylight Time (UTC+02:00)"


def test_past_event():
    event = load("kanddinsky-2018")
    assert event.name == "KanDDDinsky"
    assert event.event_end == "2018-10-19"
    assert event.location.endswith("Berlin, Germany")
    assert event.cfp_open == "2018-02-01"


def test_page_without_an_event_is_an_error():
    with pytest.raises(ParseError):
        parse_event("<html><body><h1>Sessionize</h1></body></html>", "missing")
