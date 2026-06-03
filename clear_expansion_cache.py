"""Delete cache/game_metadata/<id>.json for every owned EXPANSION in
collection.csv. Standalones are left alone.

Use when you've changed scrape_metadata.py to capture a new field and want
to force a re-scrape of expansions on the next build_collection.py run.

Lists what it will delete first and asks for confirmation. Skips files that
don't exist.

Run from PyCharm.
"""

import csv

import config


def main():
    csv_path = config.PROJECT_ROOT / "collection.csv"
    if not csv_path.exists():
        raise RuntimeError(
            "collection.csv not found at the project root.")

    expansions = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("own") != "1":
                continue
            if row.get("itemtype") != "expansion":
                continue
            expansions.append({
                "bgg_id": int(row["objectid"]),
                "title": row.get("objectname", ""),
            })
    print("Found {} owned expansion(s) in collection.csv.".format(len(expansions)))

    to_delete = []
    missing = []
    for exp in expansions:
        path = config.CACHE_METADATA_DIR / "{}.json".format(exp["bgg_id"])
        if path.exists():
            to_delete.append((exp, path))
        else:
            missing.append(exp)

    if missing:
        print()
        print("Already absent from cache ({}):".format(len(missing)))
        for exp in missing:
            print("  bgg_id={} '{}'".format(exp["bgg_id"], exp["title"]))

    if not to_delete:
        print()
        print("Nothing to delete.")
        return

    print()
    print("Will DELETE {} file(s):".format(len(to_delete)))
    for exp, path in to_delete:
        print("  {} ({})".format(path.name, exp["title"]))

    print()
    answer = input("Proceed? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted.")
        return

    deleted = 0
    for exp, path in to_delete:
        try:
            path.unlink()
            deleted += 1
        except OSError as e:
            print("  failed to delete {}: {}".format(path.name, e))
    print()
    print("Deleted {} cache file(s).".format(deleted))
    print("Run build_collection.py to re-scrape them.")


if __name__ == "__main__":
    main()