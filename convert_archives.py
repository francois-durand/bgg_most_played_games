"""One-shot (re-runnable) converter: old published pivot.csv -> archive JSON.

Each past edition lives in a repo folder whose name ends in 'April_<YYYY>',
e.g. '2024_05_03_Published_version_April_2024/pivot.csv'. The leading date is
when the archive was made and is ignored; the 'April_<YYYY>' part is the
edition year (= the data window end).

For each such folder we read pivot.csv (delimiter ';', rows already sorted by
points descending) and write archive/<YYYY>.json containing, per game:
    {rank, bgg_id, title, points}
rank is the 1-based row position. bgg_id is parsed from the url column.

Run from PyCharm. Re-running overwrites the archive JSONs (safe).
"""

import csv
import json
import re

import config

# Where the old edition folders live (inside the repo). Adjust if needed.
ARCHIVES_SOURCE_DIR = config.PROJECT_ROOT

# Where to write the JSON archives.
ARCHIVE_DIR = config.PROJECT_ROOT / "archive"

_BGG_ID_RE = re.compile(r"/(?:boardgame|boardgameexpansion)/(\d+)")
_EDITION_RE = re.compile(r"April_(\d{4})")


def _parse_int_or_none(value):
    """Return int(value) or None if value is empty or 'not applicable'."""
    if value is None:
        return None
    s = value.strip()
    if not s or s.lower() == "not applicable":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_float_or_none(value):
    if value is None:
        return None
    s = value.strip()
    if not s or s.lower() == "not applicable":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_pivot(path):
    """Read a pivot.csv and return a list of dict entries (one per game).

    Each entry: rank, bgg_id, title, points, months_in_top_100, peak_position,
    months_in_top_10, current_position_in_top_100, months_since_leaving_top_100.

    'not applicable' values (current_position_in_top_100 for games no longer in
    the top 100, months_since_leaving_top_100 for games still in it) become null.
    """
    entries = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for i, row in enumerate(reader, start=1):
            url = (row.get("url") or "").strip()
            m = _BGG_ID_RE.search(url)
            bgg_id = int(m.group(1)) if m else None
            entries.append({
                "rank": i,
                "bgg_id": bgg_id,
                "title": (row.get("title") or "").strip(),
                "points": _parse_float_or_none(row.get("points")),
                "months_in_top_100": _parse_int_or_none(
                    row.get("months in top 100")),
                "peak_position": _parse_int_or_none(row.get("peak position")),
                "months_in_top_10": _parse_int_or_none(
                    row.get("months in top 10")),
                "current_position_in_top_100": _parse_int_or_none(
                    row.get("current position in top 100")),
                "months_since_leaving_top_100": _parse_int_or_none(
                    row.get("months since leaving top 100")),
            })
    return entries


def find_edition_folders(source_dir):
    """Yield (edition_year, pivot_path) for each archive folder found."""
    for child in sorted(source_dir.iterdir()):
        if not child.is_dir():
            continue
        m = _EDITION_RE.search(child.name)
        if not m:
            continue
        pivot = child / "pivot.csv"
        if pivot.exists():
            yield int(m.group(1)), pivot
        else:
            print("  [warn] no pivot.csv in {}".format(child.name))


def convert_all():
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    found = list(find_edition_folders(ARCHIVES_SOURCE_DIR))
    if not found:
        print("No edition folders (matching 'April_<YYYY>') found in {}.".format(
            ARCHIVES_SOURCE_DIR))
        return
    for year, pivot in found:
        entries = parse_pivot(pivot)
        out_path = ARCHIVE_DIR / "{}.json".format(year)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"edition": year, "games": entries}, f,
                      ensure_ascii=False, indent=2)
        n_missing = sum(1 for e in entries if e["bgg_id"] is None)
        print("Edition {}: {} games -> {}{}".format(
            year, len(entries), out_path,
            " ({} without bgg_id!)".format(n_missing) if n_missing else ""))
    print("Done.")


if __name__ == "__main__":
    convert_all()