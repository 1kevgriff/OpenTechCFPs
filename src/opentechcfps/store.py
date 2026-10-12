from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from opentechcfps.models import is_past, reference_date


def load(source_dir: Path) -> dict[str, dict]:
    records = {}
    for path in [source_dir / "active.json", *sorted((source_dir / "archive").glob("*.json"))]:
        if path.exists():
            for record in json.loads(path.read_text(encoding="utf-8")):
                records[record["id"]] = record
    return records


def save(source_dir: Path, records: dict[str, dict], today: date) -> None:
    """Active events in one file, past events by year. Output is byte-stable for equal input."""
    active, archive = [], defaultdict(list)
    for record in records.values():
        if is_past(record, today):
            ref = reference_date(record)
            archive[str(ref.year) if ref else "undated"].append(record)
        else:
            active.append(record)

    _write(source_dir / "active.json", active)
    for year, items in archive.items():
        _write(source_dir / "archive" / f"{year}.json", items)


def _write(path: Path, records: list[dict]) -> None:
    # One record per line keeps the 3-hourly diffs to the lines that really changed.
    lines = [
        json.dumps(r, ensure_ascii=False, separators=(",", ":"))
        for r in sorted(records, key=lambda r: r["id"])
    ]
    text = "[\n" + ",\n".join(lines) + "\n]\n" if lines else "[]\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
