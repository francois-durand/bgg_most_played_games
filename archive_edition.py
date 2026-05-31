"""Freeze the current edition: write archive/<year>.json and move the
generated artifacts to a dated published-version folder.

Run this AFTER you're happy with the edition — i.e. after building scores,
games, web data, and the geeklist; reviewing them; and publishing them on
BGG. It freezes the edition in two ways:

  1. Writes archive/<year>.json (minimal fields needed by future deltas).
     This file MUST be committed: it is the source of truth used by next
     year's build_scores.py and build_web_data.py.

  2. Creates a folder named YYYY_MM_DD_Published_version_April_YYYY at the
     repo root (YYYY_MM_DD = today, the trailing YYYY = edition year) and
     MOVES scores.json, games.json, and geeklist.txt into it. This mirrors
     the historical published-version folders. After the move, the project
     root is clean and ready for the next edition.

Safety:
  - Refuses to overwrite an existing archive/<year>.json unless OVERWRITE
    is set to True (in case you intentionally regenerate).
  - Refuses to overwrite an existing published-version folder.
  - Refuses to run if scores.json is missing.
  - Moves files; refuses to move if the source doesn't exist.

Run from PyCharm.
"""

import datetime as _dt
import json
import shutil

import config


# Set to True only when you deliberately want to overwrite an existing archive
# (e.g. you fixed a bug and want to re-freeze the same edition). Leave False
# in normal operation.
OVERWRITE = False


# Fields preserved in the archive (in this order). Kept minimal because
# this file is the input to future-edition deltas and nothing else.
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

# Artifacts that get moved into the dated folder. All produced by the
# build/* and prepare_* scripts; all listed in .gitignore at the root.
ARTIFACTS_TO_MOVE = ["scores.json", "games.json", "geeklist.txt"]


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

    # 1) Write archive/<year>.json
    _write_archive_json(scores, edition)

    # 2) Move scores.json / games.json / geeklist.txt into a dated folder.
    _move_artifacts_to_dated_folder(edition)

    print()
    print("Don't forget to:")
    print("  - commit archive/{}.json (it's the source of truth for next ".format(edition)
          + "year's deltas)")
    print("  - commit the new published-version folder")


def _write_archive_json(scores, edition):
    archive_dir = config.PROJECT_ROOT / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    out_path = archive_dir / "{}.json".format(edition)
    if out_path.exists() and not OVERWRITE:
        raise RuntimeError(
            "{} already exists. Set OVERWRITE=True in {} to replace it.".format(
                out_path, __file__))

    archived_games = [
        {k: g.get(k) for k in ARCHIVE_FIELDS}
        for g in scores.get("games", [])
    ]
    payload = {"edition": edition, "games": archived_games}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("Wrote archive: {} ({} games).".format(out_path, len(archived_games)))


def _move_artifacts_to_dated_folder(edition):
    today = _dt.date.today().strftime("%Y_%m_%d")
    folder_name = "{}_Published_version_April_{}".format(today, edition)
    folder = config.PROJECT_ROOT / folder_name
    if folder.exists():
        raise RuntimeError(
            "{} already exists. Move it aside, or rename today's archive "
            "manually.".format(folder))
    folder.mkdir()

    moved = []
    for name in ARTIFACTS_TO_MOVE:
        src = config.PROJECT_ROOT / name
        if not src.exists():
            raise RuntimeError(
                "{} not found at project root. Did you skip a build step?"
                .format(src))
        shutil.move(str(src), str(folder / name))
        moved.append(name)

    print("Moved {} artifact(s) to {}: {}".format(
        len(moved), folder, ", ".join(moved)))


if __name__ == "__main__":
    archive_edition()