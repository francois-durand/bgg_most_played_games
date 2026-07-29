"""Maintain my_collection_extra_info.json: scaffolds new entries.

Reads collection.csv to know which bgg_ids you own, then:
  - If my_collection_extra_info.json doesn't exist, creates it with all your
    owned bgg_ids as {"english": "<title>", "french": "<title>", "age": null}.
  - If it exists, leaves all existing entries alone, ADDS new bgg_ids found
    in collection.csv, and REFRESHES the English title from the CSV (in case
    BGG renames a game).

The "french" field defaults to the English title (edit it by hand when the
French title differs). The "age" field defaults to null: it is your own
estimated minimum age for the game, left null until you explicitly set it,
so that null always means "no manual estimate", never a copied BGG value.

It never overwrites a french or age value you've set, and never removes
entries (so that if you sell a game and then re-buy it, your old values are
still there).

Run from PyCharm.
"""

import csv
import json

import config


EXTRA_INFO_PATH = config.PROJECT_ROOT / "my_collection_extra_info.json"


def maintain_my_collection_extra_info():
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

    # Load existing my_collection_extra_info.json (or start empty).
    if EXTRA_INFO_PATH.exists():
        with open(EXTRA_INFO_PATH, encoding="utf-8") as f:
            data = json.load(f)
        n_existing = len(data) - (1 if "_comment" in data else 0)
        print("Loaded {} existing entries from {}".format(
            n_existing, EXTRA_INFO_PATH.name))
    else:
        data = {
            "_comment": (
                "Maintained manually. Each entry maps a BGG ID to extra info "
                "for the collection page: an English title (from the BGG "
                "collection export), a French title (defaults to the "
                "English one; edit it when it differs), and your own "
                "estimated minimum age (null until you set it by hand; "
                "never auto-filled from BGG). Run "
                "maintain_my_collection_extra_info.py to scaffold new "
                "entries and refresh English titles when you update "
                "collection.csv."
            )
        }
        print("Creating {} from scratch.".format(EXTRA_INFO_PATH.name))

    # For every owned bgg_id, ensure an entry exists; refresh english title.
    # Existing french/age values are preserved.
    added = 0
    for bgg_id in sorted(owned):
        key = str(bgg_id)
        if key not in data:
            data[key] = {
                "english": owned[bgg_id],
                "french": owned[bgg_id],
                "age": None,
            }
            added += 1
        else:
            # Refresh english (BGG may have renamed); keep french/age.
            entry = data[key]
            # Be tolerant if an old format slipped in (a plain string/null).
            if not isinstance(entry, dict):
                data[key] = {
                    "english": owned[bgg_id],
                    "french": entry,
                    "age": None,
                }
            else:
                entry["english"] = owned[bgg_id]
                if not entry.get("french"):
                    entry["french"] = owned[bgg_id]
                entry.setdefault("age", None)
    if added:
        print("Added {} new bgg_id stub(s).".format(added))

    # Write back. Comment first, then numeric ids sorted as int.
    ordered = {}
    if "_comment" in data:
        ordered["_comment"] = data["_comment"]
    for k in sorted([k for k in data if k != "_comment"], key=int):
        ordered[k] = data[k]
    with open(EXTRA_INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
    print("Wrote {}.".format(EXTRA_INFO_PATH.name))


if __name__ == "__main__":
    maintain_my_collection_extra_info()
