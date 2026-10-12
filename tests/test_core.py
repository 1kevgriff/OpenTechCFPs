from datetime import UTC, date, datetime

from opentechcfps import countries, store
from opentechcfps.models import is_past, status
from opentechcfps.tags import Tagger

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def record(**overrides) -> dict:
    base = {
        "id": "sessionize:a",
        "name": "A",
        "event_start": "2027-04-21",
        "event_end": None,
        "cfp_open": "2026-10-01",
        "cfp_close_utc": "2026-11-27T22:59:00Z",
    }
    return base | overrides


def test_status_follows_the_cfp_window():
    assert status(record(), NOW) == "open"
    assert status(record(cfp_open="2026-10-13"), NOW) == "upcoming"
    assert status(record(cfp_close_utc="2026-10-12T11:59:00Z"), NOW) == "closed"
    assert status(record(cfp_close_utc=None), NOW) == "unknown"


def test_event_stays_current_until_its_last_date():
    today = date(2026, 10, 12)
    assert not is_past(record(), today)
    assert not is_past(record(event_start="2026-10-12", cfp_close_utc=None), today)
    assert is_past(record(event_start="2026-10-11", cfp_close_utc="2026-09-01T00:00:00Z"), today)
    # A rolling call can outlive the first listed meetup date.
    assert not is_past(record(event_start="2026-01-12"), today)
    assert is_past(record(event_start=None, cfp_close_utc=None), today)


def test_tags_match_whole_words_and_symbols():
    tagger = Tagger(
        {"dotnet": [".net", "c#"], "java": ["java"], "ai": ["AI"], "data": ["power bi"]}
    )
    assert tagger.tag("All about .NET and C# today") == ["dotnet"]
    assert tagger.tag("JavaScript only") == []
    assert tagger.tag("Java, obviously") == ["java"]
    assert tagger.tag("visit example.net") == []
    assert tagger.tag("Power BI and AI") == ["ai", "data"]
    # Italian "ai" is a preposition, not a topic.
    assert tagger.tag("Benvenuti ai nostri eventi") == []


def test_country_comes_from_the_last_part_of_the_location():
    assert countries.resolve("ICE Krakow Congress Centre, Kraków, Poland") == "PL"
    assert countries.resolve("Alpharetta, Georgia, United States") == "US"
    assert countries.resolve("London, UK") == "GB"
    assert countries.resolve("Istanbul, Türkiye") == "TR"
    # State abbreviations must not be read as country codes.
    assert countries.resolve("Los Angeles, CA") is None
    assert countries.resolve(None) is None


def test_online_when_no_venue_or_venue_says_so():
    assert countries.is_online(None)
    assert countries.is_online("Online")
    assert not countries.is_online("Oslo, Norway")


def test_store_splits_by_date_and_round_trips_byte_for_byte(tmp_path):
    records = {
        "sessionize:b": record(id="sessionize:b", name="Bé"),
        "sessionize:a": record(),
        "sessionize:old": record(
            id="sessionize:old", event_start="2018-10-17", cfp_close_utc="2018-03-31T21:59:00Z"
        ),
        "sessionize:none": record(id="sessionize:none", event_start=None, cfp_close_utc=None),
    }
    today = date(2026, 10, 12)
    store.save(tmp_path, records, today)

    active = (tmp_path / "active.json").read_bytes()
    assert active.index(b"sessionize:a") < active.index(b"sessionize:b")
    assert "Bé".encode() in active and b"\r" not in active
    assert (tmp_path / "archive" / "2018.json").exists()
    assert (tmp_path / "archive" / "undated.json").exists()

    loaded = store.load(tmp_path)
    assert loaded == records
    store.save(tmp_path, loaded, today)
    assert (tmp_path / "active.json").read_bytes() == active
