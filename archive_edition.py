"""Freeze the current scores.json as a permanent archive entry.

Once you're happy with an edition (after running build_scores.py and reviewing
scores.json), run this to copy it into archive/<edition>.json. The archive is
the source of truth for future editions' deltas: it must never be regenerated
on the fly (see README), only frozen and committed.

The archive keeps only the minimal information needed for deltas + readability:
  rank, bgg_id, title, points,
  months_in_top_100, peak_position, months_in_top_10,
  current_position_in_top_100, months_since_leaving_top_100

(Same shape as the JSONs produced by convert_archives.py from old CSVs.)

Safety:
  - Refuses to overwrite an existing archive/<edition>.json unless OVERWRITE
    is set to True below.
  - Refuses to run if scores.json is absent.

Run from PyCharm.
"""

import json

import config


# Set to True only when you deliberately want to overwrite an existing archive
# (e.g. you fixed a bug and want to re-freeze the same edition). Leave False
# in normal operation.
OVERWRITE = False


# Fields preserved in the archive (in this order).
ARCHIVE_FIELDS = [
    "rank",
    "bgg_id",
    "title",
    "points",
    "months_in_top_100",
    "peak_position",
    "months_in_top_10",
    "current_position_in_top_100",
    "months_since_leaving_top_100",
]


def archive_edition():
    scores_path = config.PROJECT_ROOT / "scores.json"
    if not scores_path.exists():
        raise RuntimeError(
            "scores.json not found. Run build_scores.py first.")

    with open(scores_path, encoding="utf-8") as f:
        scores = json.load(f)
    edition = scores.get("edition")
    if not isinstance(edition, int):
        raise RuntimeError(
            "scores.json has no integer 'edition' field. Aborting.")

    archive_dir = config.PROJECT_ROOT / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    out_path = archive_dir / "{}.json".format(edition)
    if out_path.exists() and not OVERWRITE:
        raise RuntimeError(
            "{} already exists. Set OVERWRITE=True in {} to replace it.".format(
                out_path, __file__))

    # Project each game to the archive shape.
    archived_games = []
    for g in scores.get("games", []):
        archived_games.append({k: g.get(k) for k in ARCHIVE_FIELDS})

    payload = {"edition": edition, "games": archived_games}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("Archived edition {}: {} games -> {}".format(
        edition, len(archived_games), out_path))
    print("Commit it to keep the archive immutable.")


if __name__ == "__main__":
    archive_edition()