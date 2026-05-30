"""Merge scores.json and games.json into a single web_data.json for the web UI.

Joins the per-game ranking info (rank, deltas, history aggregates) with the
per-game metadata (image, players, playtime, age, weight, credits, etc.) and
keeps only the top 250 — the cutoff used by the published geeklist.

The output is a flat list, one entry per game, ordered by rank. It is the
single source of truth that the static web page consumes. Putting the join in
Python (rather than in browser JS) keeps the JS layer simple and isolates all
cross-file logic on the build side.

We keep only the lists the page will display (designers, solo_designers,
artists) and drop publishers/mechanics/categories/families — but we fold all
of them into a normalized `search_blob` so the page can full-text search them
without storing them explicitly. This shrinks the file noticeably.

Run from PyCharm. Requires scores.json and games.json at the project root
(run build_scores.py and build_games.py first).
"""

import json
import re
import unicodedata

import config


TOP_N = 250  # cutoff to match the published geeklist


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _normalize_text(s):
    """Lowercase + strip accents + collapse whitespace, for search matching.

    Examples:
      'Mécanique'   -> 'mecanique'
      '7 Wonders'   -> '7 wonders'
      'Antoine\\nBauza' -> 'antoine bauza'
    The JS side must apply the same transformation to the user query.
    """
    if s is None:
        return ""
    # NFKD splits accented chars into base + combining mark; drop the marks.
    nfkd = unicodedata.normalize("NFKD", str(s))
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_str = ascii_str.lower()
    return re.sub(r"\s+", " ", ascii_str).strip()


def _names(items):
    """Pull 'name' from a list of {name, id} dicts; ignore non-strings."""
    out = []
    for it in items or []:
        n = it.get("name") if isinstance(it, dict) else None
        if n:
            out.append(n)
    return out


def _build_search_blob(g, title, year):
    """Concatenate every searchable string for `g`, normalize, return one string.

    Includes: title, year (as string), all names from designers, solo_designers,
    artists, publishers, mechanics, categories, families. Duplicates after
    normalization are removed to keep the blob compact.
    """
    parts = [title or ""]
    if year is not None:
        parts.append(str(year))
    for field in ("designers", "solo_designers", "artists", "publishers",
                  "mechanics", "categories", "families"):
        parts.extend(_names(g.get(field)))

    # Normalize each part, then dedupe.
    seen = set()
    tokens = []
    for p in parts:
        n = _normalize_text(p)
        if n and n not in seen:
            seen.add(n)
            tokens.append(n)
    return " ".join(tokens)


def build_web_data():
    scores_path = config.PROJECT_ROOT / "scores.json"
    games_path = config.PROJECT_ROOT / "games.json"
    if not scores_path.exists():
        raise RuntimeError(
            "scores.json not found. Run build_scores.py first.")
    if not games_path.exists():
        raise RuntimeError(
            "games.json not found. Run build_games.py first.")

    scores = _load(scores_path)
    games = _load(games_path)
    edition = scores.get("edition")

    games_by_id = {g["bgg_id"]: g for g in games.get("games", [])}

    out = []
    missing_meta = []
    for s in scores.get("games", []):
        if s["rank"] > TOP_N:
            break  # scores list is sorted by rank, so we can stop here
        bgg_id = s["bgg_id"]
        g = games_by_id.get(bgg_id)
        if g is None:
            missing_meta.append(bgg_id)
            continue

        # Title: prefer the metadata's primary_name (BGG canonical English),
        # fall back to the rankings title.
        title = g.get("title") or s.get("title")

        # From the published-list perspective, "previous edition" means the
        # previous published top-N. So a game whose previous overall rank was
        # outside the top-N is, for the reader, a new entry — even if its
        # actual previous_rank is e.g. 412. Override here so the web UI shows
        # "NEW" consistently for anyone the reader couldn't have seen before.
        previous_rank = s.get("previous_rank")
        rank_delta = s.get("rank_delta")
        if previous_rank is not None and previous_rank > TOP_N:
            previous_rank = None
            rank_delta = "NEW"

        entry = {
            # Identity & visual
            "bgg_id": bgg_id,
            "title": title,
            "year": g.get("year"),
            "image_url": g.get("image_url"),
            "bgg_url": "https://boardgamegeek.com/boardgame/{}".format(bgg_id),

            # Ranking (from scores.json)
            "rank": s["rank"],
            "points": s["points"],
            "previous_rank": previous_rank,
            "rank_delta": rank_delta,
            "months_in_top_100": s.get("months_in_top_100"),
            "months_in_top_10": s.get("months_in_top_10"),
            "peak_position": s.get("peak_position"),
            "current_position_in_top_100": s.get("current_position_in_top_100"),
            "months_since_leaving_top_100": s.get("months_since_leaving_top_100"),

            # Displayable metadata (from games.json)
            "players": g.get("players"),
            "playing_time": g.get("playing_time"),
            "age": g.get("age"),
            "weight": g.get("weight"),

            # Credit lists that we DO display on each card.
            "designers": g.get("designers") or [],
            "solo_designers": g.get("solo_designers") or [],
            "artists": g.get("artists") or [],

            # Single normalized string aggregating every searchable text
            # (title, year, all credit/classification names including
            # publishers/mechanics/categories/families which are NOT kept as
            # separate fields above). The JS does a substring match on this
            # after applying the same normalization to the user query.
            "search_blob": _build_search_blob(g, title, g.get("year")),

            # Structured lists for the "Match" disclosure: when a search
            # query matches via one of these (publisher / mechanic /
            # category / family), the web UI shows the matching names so
            # the reader understands why the game appeared. Kept as full
            # {name, id, type} entries to allow direct BGG links.
            "search_index": {
                "publishers": g.get("publishers") or [],
                "mechanics":  g.get("mechanics")  or [],
                "categories": g.get("categories") or [],
                "families":   g.get("families")   or [],
            },
        }
        out.append(entry)

    if missing_meta:
        print("WARNING: {} top-{} games have no metadata: {}".format(
            len(missing_meta), TOP_N, missing_meta[:10]))

    payload = {"edition": edition, "top_n": TOP_N, "games": out}
    docs_dir = config.PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_path = docs_dir / "web_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("Wrote {} ({} games, edition {}).".format(out_path, len(out), edition))


if __name__ == "__main__":
    build_web_data()