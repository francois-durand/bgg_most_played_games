"""Find games whose community / best player counts have a 'hole'.

E.g. a game playable at 1, 3, 4 (but not 2) — its values are [1, 3, 4],
which differs from list(range(min, max+1)) = [1, 2, 3, 4]. Just a curiosity
report, not a sign of a bug.

Reads games.json. Run from PyCharm.
"""

import json

import config


def is_non_contiguous(rng):
    """rng is the {min, max, values} dict (or None). True iff there's a hole."""
    if not rng or "values" not in rng:
        return False
    expected = list(range(rng["min"], rng["max"] + 1))
    return rng["values"] != expected


def main():
    path = config.PROJECT_ROOT / "games.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    n_total = 0
    n_with_hole = 0
    for g in data.get("games", []):
        n_total += 1
        players = g.get("players") or {}
        community = players.get("community")
        best = players.get("best")
        community_hole = is_non_contiguous(community)
        best_hole = is_non_contiguous(best)
        if community_hole or best_hole:
            n_with_hole += 1
            print("  {} (id {}):".format(g.get("title"), g.get("bgg_id")))
            if community_hole:
                print("    community: min={} max={} values={}".format(
                    community["min"], community["max"], community["values"]))
            if best_hole:
                print("    best:      min={} max={} values={}".format(
                    best["min"], best["max"], best["values"]))

    print("\nScanned {} games, {} with a non-contiguous player-count range."
          .format(n_total, n_with_hole))


if __name__ == "__main__":
    main()