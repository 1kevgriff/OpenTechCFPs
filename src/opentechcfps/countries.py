from __future__ import annotations

import re
from functools import cache

import pycountry

ALIASES = {
    "usa": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "united states of america": "US",
    "uk": "GB",
    "u.k.": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "great britain": "GB",
    "russia": "RU",
    "south korea": "KR",
    "north korea": "KP",
    "turkey": "TR",
    "türkiye": "TR",
    "czech republic": "CZ",
    "vietnam": "VN",
    "iran": "IR",
    "syria": "SY",
    "laos": "LA",
    "moldova": "MD",
    "bolivia": "BO",
    "venezuela": "VE",
    "tanzania": "TZ",
    "taiwan": "TW",
    "macedonia": "MK",
    "palestine": "PS",
    "ivory coast": "CI",
    "the netherlands": "NL",
    "holland": "NL",
    "uae": "AE",
    "kosovo": "XK",
    "democratic republic of the congo": "CD",
    "dr congo": "CD",
    "brasil": "BR",
    "deutschland": "DE",
    "españa": "ES",
    "italia": "IT",
    "méxico": "MX",
}

ONLINE = re.compile(r"\b(online|virtual|remote)\b", re.IGNORECASE)


@cache
def _names() -> dict[str, str]:
    # Names only. Alpha-2 codes are left out on purpose: "CA", "IN" and "DE" are far more
    # often US states than countries at the end of an address.
    names = {}
    for country in pycountry.countries:
        for attr in ("name", "official_name", "common_name"):
            value = getattr(country, attr, None)
            if value:
                names[value.lower()] = country.alpha_2
    names.update(ALIASES)
    return names


def resolve(location: str | None) -> str | None:
    """ISO 3166-1 alpha-2 for the last comma-separated part of a location, if it is a country."""
    if not location:
        return None
    last = location.rsplit(",", 1)[-1].strip().lower()
    return _names().get(last)


def is_online(location: str | None) -> bool:
    return not location or bool(ONLINE.search(location))


def name_of(code: str) -> str:
    country = pycountry.countries.get(alpha_2=code)
    if not country:
        return code
    return getattr(country, "common_name", None) or country.name
