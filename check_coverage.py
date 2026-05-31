"""Coverage report on games.json: how many games have each field set.

Useful for detecting regressions in BGG's HTML structure after a scrape:
if a field's coverage drops below its expected threshold, the scraper or
parser is probably missing something. Run this after build_games.py (or
as part of main.py).

The report flags every field whose coverage is below an expected threshold
with a "WARN" marker. For every field that has missing values, it lists
the bgg_ids that lack it, so you can spot-check them on BGG.

Run from PyCharm. Reads games.json at the project root; doesn't touch
anything else.
"""

import json

import config


# (label, getter, threshold_pct)
# threshold_pct is the minimum coverage expected; below that, we WARN.
# Getter returns truthy iff the field is "present" — meaning it has actual
# data, not just an empty container or None.
FIELDS = [
    # Identification (must be 100%)
    ("bgg_id",                 lambda g: g.get("bgg_id"),                                       100),
    ("title",                  lambda g: g.get("title"),                                        100),
    ("image_url",              lambda g: g.get("image_url"),                                    100),
    ("year",                   lambda g: g.get("year"),                                         100),
    ("publishers",             lambda g: bool(g.get("publishers")),                             100),

    # Almost always present
    ("designers",              lambda g: bool(g.get("designers")),                               99),

    # Usually present
    ("players.official",       lambda g: (g.get("players") or {}).get("official"),               95),
    ("playing_time",           lambda g: bool(g.get("playing_time")),                            95),
    ("age.official",           lambda g: (g.get("age") or {}).get("official") is not None,       95),

    # Variable — community-sourced or optional credits
    ("weight",                 lambda g: g.get("weight") is not None,                            80),
    ("artists",                lambda g: bool(g.get("artists")),                                 80),
    ("mechanics",              lambda g: bool(g.get("mechanics")),                               80),
    ("categories",             lambda g: bool(g.get("categories")),                              80),
    ("families",               lambda g: bool(g.get("families")),                                80),

    # Community fields (no strong expectation)
    ("players.community",      lambda g: bool((g.get("players") or {}).get("community")),         0),
    ("players.best",           lambda g: bool((g.get("players") or {}).get("best")),              0),
    ("age.community",          lambda g: (g.get("age") or {}).get("community") is not None,       0),
]

EXPECTED_GAME_COUNT = 250


def check_coverage():
    games_path = config.PROJECT_ROOT / "games.json"
    if not games_path.exists():
        raise RuntimeError(
            "games.json not found. Run build_games.py first.")

    with open(games_path, encoding="utf-8") as f:
        payload = json.load(f)
    games = payload.get("games", [])
    n = len(games)

    print()
    print("=" * 70)
    print("Coverage report for games.json")
    print("=" * 70)

    # Sanity: total game count.
    if n != EXPECTED_GAME_COUNT:
        print("WARN: {} games found (expected ~{}). "
              "Check scrape_rankings.".format(n, EXPECTED_GAME_COUNT))
    else:
        print("{} games total.".format(n))
    print()

    # Header.
    print("  {:<20s}  {:>15s}  {:>6s}  {}".format(
        "field", "coverage", "thr.", "status"))
    print("  " + "-" * 60)

    # We collect the list of missing IDs per field so we can print them
    # after the table.
    missing_per_field = []

    for label, getter, threshold in FIELDS:
        present = sum(1 for g in games if getter(g))
        pct = 100.0 * present / n if n else 0.0
        status = "OK" if pct >= threshold else "WARN"
        coverage_str = "{}/{} ({:.1f}%)".format(present, n, pct)
        print("  {:<20s}  {:>15s}  {:>5d}%  {}".format(
            label, coverage_str, threshold, status))
        # Collect missing IDs for any field with at least one absence.
        if present < n:
            missing = [g.get("bgg_id") for g in games if not getter(g)]
            missing_per_field.append((label, missing))

    # Per-field listings (after the table for readability).
    if missing_per_field:
        print()
        print("Missing values:")
        for label, missing in missing_per_field:
            print("  {} ({} missing): {}".format(
                label, len(missing), missing))
    print()


if __name__ == "__main__":
    check_coverage()