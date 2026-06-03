"""Maintain french_titles.json: scaffolds + reports missing entries.

Reads collection.csv to know which bgg_ids you own, then:
  - If french_titles.json doesn't exist, creates it with all your owned
    bgg_ids as {"english": "<title>", "french": null}. You fill in the
    French values manually.
  - If it exists, leaves all existing entries alone, ADDS new bgg_ids
    found in collection.csv, REFRESHES the English title from the CSV
    (in case BGG renames a game), and reports which entries still need
    a French value.

It never overwrites a French value you've set, and never removes
entries (so that if you sell a game and then re-buy it, your old
French title is still there).

Run from PyCharm.
"""

import csv
import json

import config


FRENCH_TITLES_PATH = config.PROJECT_ROOT / "french_titles.json"


def main():
    csv_path = config.PROJECT_ROOT / "collection.csv"
    if not csv_path.exists():
        raise RuntimeError(
            "collection.csv not found at the project root.")

    # Load current owned items: {bgg_id: english_title}.
    owned = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("own") != "1":
                continue
            owned[int(row["objectid"])] = row.get("objectname", "")
    print("Found {} owned items in collection.csv".format(len(owned)))

    # Load existing french_titles.json (or start empty).
    if FRENCH_TITLES_PATH.exists():
        with open(FRENCH_TITLES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        n_existing = len(data) - (1 if "_comment" in data else 0)
        print("Loaded {} existing entries from {}".format(
            n_existing, FRENCH_TITLES_PATH.name))
    else:
        data = {
            "_comment": (
                "Maintained manually. Each entry maps a BGG ID to its English "
                "title (from the BGG collection export) and a French title "
                "you fill in. The collection page uses the French value; if "
                "null, it falls back to the English. Run "
                "maintain_french_titles.py to scaffold new entries and "
                "refresh English titles when you update collection.csv."
            )
        }
        print("Creating {} from scratch.".format(FRENCH_TITLES_PATH.name))

    # For every owned bgg_id, ensure an entry exists; refresh english title.
    # Existing french values are preserved.
    added = 0
    for bgg_id in sorted(owned):
        key = str(bgg_id)
        if key not in data:
            data[key] = {"english": owned[bgg_id], "french": None}
            added += 1
        else:
            # Refresh english (BGG may have renamed); keep french.
            entry = data[key]
            # Be tolerant if an old format slipped in (a plain string/null).
            if not isinstance(entry, dict):
                data[key] = {"english": owned[bgg_id], "french": entry}
            else:
                entry["english"] = owned[bgg_id]
                entry.setdefault("french", None)
    if added:
        print("Added {} new bgg_id stub(s).".format(added))

    # Write back. Comment first, then numeric ids sorted as int.
    ordered = {}
    if "_comment" in data:
        ordered["_comment"] = data["_comment"]
    for k in sorted([k for k in data if k != "_comment"], key=int):
        ordered[k] = data[k]
    with open(FRENCH_TITLES_PATH, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)

    # Report missing titles, sorted by English title for ease of editing.
    missing = []
    for bgg_id in sorted(owned):
        entry = ordered.get(str(bgg_id))
        if not isinstance(entry, dict) or not entry.get("french"):
            missing.append((bgg_id, owned[bgg_id]))
    if missing:
        print()
        print("French title still missing for {} item(s):".format(len(missing)))
        for bgg_id, eng in sorted(missing, key=lambda x: x[1].lower()):
            print("  {:>7}  '{}'".format(bgg_id, eng))
        print()
        print("Edit {} to fill them in.".format(FRENCH_TITLES_PATH.name))
    else:
        print()
        print("All owned items have a French title. Nothing to do.")


if __name__ == "__main__":
    main()