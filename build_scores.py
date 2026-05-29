"""Compute the scores for the current edition from the rankings cache.

For each game appearing in at least one monthly top 100 within the configured
window [START, END), this script computes:
  - rank, points
  - months_in_top_100, months_in_top_10
  - peak_position
  - current_position_in_top_100  (null if not in the very last month)
  - months_since_leaving_top_100 (null if still in the very last month)
  - monthly_history: list of {year, month, position}, chronological

Points formula:
    points(game) = sum over (months where the game is in the monthly top 100)
                   of rank ** (-0.5)

We also read archive/<Y>.json for every Y < END_YEAR to compute, per game:
  - previous_rank: rank in the previous edition (Y = END_YEAR - 1), or null
  - rank_delta:   previous_rank - rank, or "NEW" for games not in the previous
                  archive. (Positive = climbed, negative = dropped.)
  - edition_history: list of {edition, rank} entries (past editions where the
                     game was ranked, chronological, with the current edition
                     appended at the end).

Output: scores.json at the project root, with {"edition": <year>, "games": [...]}.
games are sorted by rank (1..N), points descending.

Parameters come from config.py:
  START_YEAR/START_MONTH, END_YEAR/END_MONTH (window; END is exclusive)
  The edition year is taken as END_YEAR (we assume the edition's window ends
  in April of that year, i.e. END_MONTH == 5).

Run from PyCharm. Run scrape_rankings.py first so the cache exists.
"""

import json

import config
from scrape_rankings import month_year_iter, month_cache_path


# --- Point function --------------------------------------------------------

def point_function(rank):
    """Points awarded for being at `rank` in a monthly top 100."""
    return rank ** (-0.5)


# --- Loading the rankings cache --------------------------------------------

def load_monthly_rankings():
    """Yield (year, month, list_of_games) for each month in [START, END).

    Raises if a month within the window is missing from the cache.
    """
    months = list(month_year_iter(
        config.START_YEAR, config.START_MONTH,
        config.END_YEAR, config.END_MONTH,
    ))
    missing = [(y, m) for (y, m) in months if not month_cache_path(y, m).exists()]
    if missing:
        formatted = ", ".join("{}-{:02d}".format(y, m) for (y, m) in missing[:10])
        more = " ..." if len(missing) > 10 else ""
        raise RuntimeError(
            "Rankings cache is incomplete: {} month(s) missing within "
            "[{}-{:02d}, {}-{:02d}): {}{}. Run scrape_rankings.py first.".format(
                len(missing),
                config.START_YEAR, config.START_MONTH,
                config.END_YEAR, config.END_MONTH,
                formatted, more))
    for (y, m) in months:
        with open(month_cache_path(y, m), encoding="utf-8") as f:
            payload = json.load(f)
        yield y, m, payload.get("games", [])


# --- Per-game aggregation --------------------------------------------------

def _t_of(year, month):
    """Monotone integer time index: 1 unit = 1 month."""
    return year * 12 + month - 1


def aggregate_games():
    """Walk the cache and produce per-game aggregates (unsorted, no rank yet).

    Returns: dict bgg_id -> aggregate dict (without rank/delta yet).
    """
    # t_max: the last month included in the configured window, i.e. END - 1 month.
    t_max = _t_of(config.END_YEAR, config.END_MONTH) - 1

    games = {}
    for year, month, monthly in load_monthly_rankings():
        t = _t_of(year, month)
        for g in monthly:
            bgg_id = g["bgg_id"]
            position = g["position"]
            entry = games.get(bgg_id)
            if entry is None:
                entry = games[bgg_id] = {
                    "bgg_id": bgg_id,
                    "title": g.get("title", ""),
                    "points": 0.0,
                    "months_in_top_100": 0,
                    "months_in_top_10": 0,
                    "peak_position": position,
                    "_last_t": t,           # most recent t we've seen
                    "_at_t_max_position": None,  # filled below
                    "monthly_history": [],
                }
            entry["points"] += point_function(position)
            entry["months_in_top_100"] += 1
            if position <= 10:
                entry["months_in_top_10"] += 1
            if position < entry["peak_position"]:
                entry["peak_position"] = position
            if t > entry["_last_t"]:
                entry["_last_t"] = t
            if t == t_max:
                entry["_at_t_max_position"] = position
            entry["monthly_history"].append({
                "year": year, "month": month, "position": position,
            })
            # Keep the most recent title (in case of renames).
            entry["title"] = g.get("title", entry["title"])

    # Finalize per-game fields that need t_max.
    for entry in games.values():
        entry["current_position_in_top_100"] = entry["_at_t_max_position"]
        if entry["_at_t_max_position"] is not None:
            # Still in the last month: "months since leaving" is not applicable.
            entry["months_since_leaving_top_100"] = None
        else:
            entry["months_since_leaving_top_100"] = t_max - entry["_last_t"]
        # monthly_history is appended in cache iteration order; the cache files
        # are read sorted by (year, month), so it's already chronological.
        entry.pop("_last_t", None)
        entry.pop("_at_t_max_position", None)

    return games


# --- Ranking ---------------------------------------------------------------

def rank_games(games):
    """Return a list of game dicts sorted by points descending, with rank set."""
    ranked = sorted(games.values(), key=lambda g: g["points"], reverse=True)
    for i, g in enumerate(ranked, start=1):
        g["rank"] = i
    return ranked


# --- Deltas vs previous edition --------------------------------------------

def _load_archives(edition_year):
    """Load all archive/<Y>.json with Y < edition_year. Returns list of dicts
    {edition, rank_by_id} sorted by edition ascending. Crashes if Y-1 missing.
    """
    archives = []
    archive_dir = config.PROJECT_ROOT / "archive"
    if archive_dir.exists():
        for path in sorted(archive_dir.glob("*.json")):
            try:
                year = int(path.stem)
            except ValueError:
                continue
            if year >= edition_year:
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            rank_by_id = {entry["bgg_id"]: entry["rank"]
                          for entry in data.get("games", [])
                          if entry.get("bgg_id") is not None}
            archives.append({"edition": year, "rank_by_id": rank_by_id})

    # The immediately-previous edition (Y-1) is required.
    if not archives or archives[-1]["edition"] != edition_year - 1:
        raise RuntimeError(
            "Previous archive archive/{}.json not found. Cannot compute deltas. "
            "Convert or generate it first (e.g. convert_archives.py for old "
            "editions, or archive the previous edition's scores).".format(
                edition_year - 1))
    return archives


def attach_deltas_and_history(ranked_games, edition_year):
    """Add previous_rank, rank_delta and edition_history to each game.

    Uses every archive/<Y>.json with Y < edition_year. The immediately-previous
    edition (Y-1) must exist; older ones contribute to edition_history only.

    rank_delta = previous_rank - rank  (positive = climbed up).
    Games new to the current edition get rank_delta = "NEW".
    edition_history is a list of {edition, rank} entries, chronological,
    listing past editions where the game was ranked (the current edition is
    appended at the end).
    """
    archives = _load_archives(edition_year)
    previous = archives[-1]  # the Y-1 archive

    for g in ranked_games:
        bgg_id = g["bgg_id"]

        # previous_rank / rank_delta from the immediately-previous edition.
        pr = previous["rank_by_id"].get(bgg_id)
        g["previous_rank"] = pr
        g["rank_delta"] = "NEW" if pr is None else pr - g["rank"]

        # Full edition history (past editions where the game was ranked),
        # plus the current edition.
        history = []
        for arch in archives:
            r = arch["rank_by_id"].get(bgg_id)
            if r is not None:
                history.append({"edition": arch["edition"], "rank": r})
        history.append({"edition": edition_year, "rank": g["rank"]})
        g["edition_history"] = history


# --- Orchestration ---------------------------------------------------------

def build_scores():
    if config.END_MONTH != 5:
        print("NOTE: END_MONTH is {} (not 5). By convention an edition ends in "
              "April; END_MONTH=5 means 'up to and including April'. Continuing "
              "anyway.".format(config.END_MONTH))

    edition_year = config.END_YEAR
    print("Building scores for edition {} (window {}-{:02d} .. {}-{:02d} excl).".format(
        edition_year, config.START_YEAR, config.START_MONTH,
        config.END_YEAR, config.END_MONTH))

    games = aggregate_games()
    print("Distinct games seen in window: {}".format(len(games)))

    ranked = rank_games(games)
    attach_deltas_and_history(ranked, edition_year)

    output = {"edition": edition_year, "games": ranked}
    out_path = config.PROJECT_ROOT / "scores.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("Wrote {} ({} games).".format(out_path, len(ranked)))


if __name__ == "__main__":
    build_scores()