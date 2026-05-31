"""Generate geeklist.txt: a ready-to-paste-into-BGG version of the current edition.

The file is structured for the workflow of manually adding items to a BGG
geeklist. Each item has:

  Line 1: "N - <title>"     — a sanity check so you know where you are
  Line 2: <bgg_id>          — paste into BGG's geeklist item search
  Line 3+: the body         — copy-paste as the item's comment

The body uses BGG geek tags ([b]...[/b]) for emphasis. Other BBCode-like
tags (italic, color, links) are not used to keep the output predictable.

The script reads scores.json and games.json (so run build_scores.py and
build_games.py first) and writes geeklist.txt at the project root. Only
the top-N entries (the same cutoff used by the web page) are included.

Run from PyCharm.
"""

import json

import config


TOP_N = 250


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    scores_path = config.PROJECT_ROOT / "scores.json"
    games_path = config.PROJECT_ROOT / "games.json"
    if not scores_path.exists():
        raise RuntimeError("scores.json not found. Run build_scores.py first.")
    if not games_path.exists():
        raise RuntimeError("games.json not found. Run build_games.py first.")

    scores = _load(scores_path)
    games = _load(games_path)
    games_by_id = {g["bgg_id"]: g for g in games.get("games", [])}

    edition = scores.get("edition")
    lines = []
    lines.append("Geeklist content for the {} edition.".format(edition))
    lines.append(
        "Workflow: for each item below, paste the bgg_id into BGG's geeklist "
        "item search to pick the game, then copy the body lines as the item's "
        "comment.")
    lines.append("")

    n_included = 0
    for s in scores.get("games", []):
        if s["rank"] > TOP_N:
            break
        g = games_by_id.get(s["bgg_id"])
        if g is None:
            # Should not happen if build_web_data.py reported no warning.
            continue
        lines.extend(_format_item(s, g))
        lines.append("")  # blank line between items
        n_included += 1

    out_path = config.PROJECT_ROOT / "geeklist.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Wrote {} ({} items, edition {}).".format(
        out_path, n_included, edition))


def _format_item(s, g):
    """Return the list of lines for one geeklist item."""
    rank = s["rank"]
    title = g.get("title") or s.get("title") or ""
    bgg_id = s["bgg_id"]

    lines = []
    lines.append("{} - {}".format(rank, title))   # sanity-check header
    lines.append(str(bgg_id))                     # paste into BGG search

    # First body line: players · time · age · year. Year goes last because the
    # other three are the gameplay tags people scan for first.
    meta_parts = []
    players = _format_players(g.get("players", {}).get("official"))
    if players:
        meta_parts.append(players)
    playtime = _format_playtime(g.get("playing_time"))
    if playtime:
        meta_parts.append(playtime)
    age = (g.get("age") or {}).get("official")
    if age:
        meta_parts.append("Age {}+".format(age))
    year = g.get("year")
    if year:
        meta_parts.append(str(year))
    lines.append(" \u00B7 ".join(meta_parts))

    # Second body line: points + delta.
    delta_text = _format_delta(s.get("rank_delta"), s.get("previous_rank"))
    points = s.get("points", 0.0)
    lines.append("[b]Points:[/b] {:.2f} \u00B7 {}".format(points, delta_text))

    # Third body line: monthly history summary.
    lines.append("[b]Monthly top by distinct players:[/b] " +
                 _format_history(s))

    return lines


def _format_players(off):
    if not off:
        return None
    mn = off.get("min")
    mx = off.get("max")
    if mn is None and mx is None:
        return None
    if mn == mx or mx is None:
        return "{} player{}".format(mn, "" if mn == 1 else "s")
    if mn is None:
        return "up to {} players".format(mx)
    return "{}\u2013{} players".format(mn, mx)


def _format_playtime(pt):
    if not pt:
        return None
    mn = pt.get("min")
    mx = pt.get("max")
    if mn is None and mx is None:
        return None
    if mn == mx or mx is None:
        return "{} min".format(mn)
    if mn is None:
        return "up to {} min".format(mx)
    return "{}\u2013{} min".format(mn, mx)


def _format_delta(delta, previous_rank):
    """Render the rank-change phrase. Cases:
        delta == "NEW"        -> "[b]New entry[/b]"
        delta == 0            -> "Same rank as last year"
        delta > 0  (climbed)  -> "Climbed N places (was #M)"
        delta < 0  (dropped)  -> "Dropped N places (was #M)"
        delta == None         -> ""  (defensive, should not happen)
    """
    if delta == "NEW":
        return "[b]New entry[/b]"
    if delta is None:
        return ""
    if delta == 0:
        return "Same rank as last year"
    n = abs(delta)
    word = "place" if n == 1 else "places"
    if delta > 0:
        return "Climbed {} {} (was #{})".format(n, word, previous_rank)
    return "Dropped {} {} (was #{})".format(n, word, previous_rank)


def _format_history(s):
    """Build the monthly-top history line. Includes:
        N months in top 100
        N in top 10
        peak #X
        currently #X  OR  left the top 100 N months ago
    All joined by " · ".
    """
    parts = []
    mt100 = s.get("months_in_top_100")
    if mt100:
        parts.append("{} months in top 100".format(mt100))
    mt10 = s.get("months_in_top_10")
    if mt10:
        parts.append("{} in top 10".format(mt10))
    peak = s.get("peak_position")
    if peak:
        parts.append("peak #{}".format(peak))

    cur = s.get("current_position_in_top_100")
    msl = s.get("months_since_leaving_top_100")
    if cur is not None:
        parts.append("currently #{}".format(cur))
    elif msl is not None:
        word = "month" if msl == 1 else "months"
        parts.append("out of top 100 for {} {}".format(msl, word))

    return " \u00B7 ".join(parts)


if __name__ == "__main__":
    main()