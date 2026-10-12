from __future__ import annotations

import re
from pathlib import Path

import yaml


class Tagger:
    """Keyword rules: tag -> keywords. A keyword with an uppercase letter is case-sensitive."""

    def __init__(self, rules: dict[str, list[str]]):
        self._rules = [(tag, _compile(keywords)) for tag, keywords in sorted(rules.items())]

    @classmethod
    def from_file(cls, path: Path) -> Tagger:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def tag(self, text: str) -> list[str]:
        return [tag for tag, patterns in self._rules if any(p.search(text) for p in patterns)]


def _compile(keywords: list[str]) -> list[re.Pattern]:
    patterns = []
    for keyword in keywords:
        keyword = str(keyword)
        flags = 0 if keyword != keyword.lower() else re.IGNORECASE
        # Not \b: keywords such as ".net" and "c#" start or end with non-word characters.
        patterns.append(re.compile(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])", flags))
    return patterns
