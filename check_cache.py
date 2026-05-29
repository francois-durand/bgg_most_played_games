"""Sanity-check the scraped caches without modifying anything.

Run this after scrape_rankings.py (and optionally after scrape_metadata.py)
to catch problems before building the final dataset:

Rankings cache (cache/monthly_rankings/*.json):
  - months missing from the configured [START, END) window
  - months whose game count != 100
  - positions not forming a clean 1..N sequence
  - empty titles, non-positive unique_users, missing bgg_id
  - duplicate bgg_ids within a month
  - any EXCLUDED_BGG_IDS that slipped through

Metadata cache (cache/game_metadata/*.json), if present:
  - games in the rankings that have no metadata file
  - metadata files missing key raw fields (image_url, players_official,
    players_secondary_text, playtime_primary_text, age_official_raw,
    weight_primary_text, credits_table)
  - metadata files with no designer link (any boardgamedesigner anywhere in
    credits_table, since the row title can be 'Designer' or 'Designers')

Nothing is deleted or changed. Run from PyCharm.
"""

import json

import config
from scrape_rankings import month_year_iter, month_cache_path


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_rankings():
    print("=" * 60)
    print("RANKINGS CACHE")
    print("=" * 60)

    months = list(month_year_iter(
        config.START_YEAR, config.START_MONTH,
        config.END_YEAR, config.END_MONTH,
    ))

    problems = 0
    all_ids = set()

    missing_months = [(y, m) for (y, m) in months
                      if not month_cache_path(y, m).exists()]
    if missing_months:
        problems += len(missing_months)
        print("\n[MISSING MONTHS] {} month(s) have no cache file:".format(
            len(missing_months)))
        for y, m in missing_months:
            print("   {}-{:02d}".format(y, m))

    for (y, m) in months:
        path = month_cache_path(y, m)
        if not path.exists():
            continue
        payload = _load(path)
        games = payload.get("games", [])
        tag = "{}-{:02d}".format(y, m)

        # Count
        if len(games) != 100:
            problems += 1
            print("\n[COUNT] {}: {} games (expected 100).".format(tag, len(games)))

        # Positions form 1..N
        positions = [g.get("position") for g in games]
        expected = list(range(1, len(games) + 1))
        if positions != expected:
            problems += 1
            print("\n[POSITIONS] {}: positions are not a clean 1..{} "
                  "sequence.".format(tag, len(games)))

        # Per-game field checks
        seen = set()
        for g in games:
            gid = g.get("bgg_id")
            if gid is None:
                problems += 1
                print("\n[FIELD] {}: a game has no bgg_id: {}".format(tag, g))
                continue
            all_ids.add(gid)
            if gid in seen:
                problems += 1
                print("\n[DUPLICATE] {}: bgg_id {} appears twice.".format(tag, gid))
            seen.add(gid)
            if not g.get("title"):
                problems += 1
                print("\n[FIELD] {}: bgg_id {} has empty title.".format(tag, gid))
            uu = g.get("unique_users")
            if uu is None or uu <= 0:
                problems += 1
                print("\n[FIELD] {}: bgg_id {} has bad unique_users={}.".format(
                    tag, gid, uu))
            if gid in config.EXCLUDED_BGG_IDS:
                problems += 1
                print("\n[EXCLUDED] {}: excluded id {} is present!".format(tag, gid))

    n_present = sum(1 for (y, m) in months if month_cache_path(y, m).exists())
    print("\nMonths present: {}/{}".format(n_present, len(months)))
    print("Distinct games across all months: {}".format(len(all_ids)))
    print("Problems found in rankings: {}".format(problems))
    return all_ids


def check_metadata(ranking_ids):
    print("\n" + "=" * 60)
    print("METADATA CACHE")
    print("=" * 60)

    if not config.CACHE_METADATA_DIR.exists():
        print("\nNo metadata cache directory yet (skip).")
        return

    cached_ids = set()
    for path in config.CACHE_METADATA_DIR.glob("*.json"):
        try:
            cached_ids.add(int(path.stem))
        except ValueError:
            pass

    missing = ranking_ids - cached_ids
    extra = cached_ids - ranking_ids
    print("\nMetadata files: {}".format(len(cached_ids)))
    print("Games in rankings without metadata: {}".format(len(missing)))
    if missing:
        sample = list(sorted(missing))[:20]
        print("   e.g. {}{}".format(sample, " ..." if len(missing) > 20 else ""))
    if extra:
        print("Metadata files not in current rankings (harmless): {}".format(
            len(extra)))

    # Field completeness on the ones we do have. These are the raw fields
    # produced by scrape_metadata.py (see that module's docstring).
    raw_fields = [
        "image_url",
        "players_official",
        "players_secondary_text",
        "playtime_primary_text",
        "age_official_raw",
        "weight_primary_text",
        "credits_table",
    ]
    incomplete = 0
    for path in config.CACHE_METADATA_DIR.glob("*.json"):
        data = _load(path)
        missing_fields = [k for k in raw_fields if not data.get(k)]
        # The credits_table key may exist but be empty, or contain a designer
        # under a row whose title varies ('Designer' vs 'Designers'). We test
        # for the presence of at least one boardgamedesigner link, by type.
        if not _has_designer(data.get("credits_table", {})):
            missing_fields.append("designer (any)")
        if missing_fields:
            incomplete += 1
            if incomplete <= 20:
                print("   [INCOMPLETE] id {} missing: {}".format(
                    data.get("bgg_id", path.stem), missing_fields))
    print("Metadata files with missing key fields: {}".format(incomplete))


def _has_designer(credits_table):
    """True if credits_table contains at least one boardgamedesigner link."""
    if not isinstance(credits_table, dict):
        return False
    for value in credits_table.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("type") == "boardgamedesigner":
                    return True
    return False


def main():
    ranking_ids = check_rankings()
    check_metadata(ranking_ids)
    print("\nDone.")


if __name__ == "__main__":
    main()