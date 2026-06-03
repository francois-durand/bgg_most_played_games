"""Build the personal-collection data for docs/collection/.

Reads collection.csv (your BGG collection export), ensures every owned item
has its metadata in cache/, then writes docs/collection/collection_data.json
that the static page consumes.

Expansion-to-standalone attachment uses BGG's own `expandsboardgame` data,
captured by scrape_metadata.py from the main /boardgame/<id> page. An owned
expansion is attached to every owned standalone that appears in its
`expands_boardgames` list. This handles reboots correctly (Dixit: Mirrors
expands both Dixit and Dixit: Odyssey, etc.).

Workflow:
  1. Export your collection as CSV from BGG and save it as collection.csv
     at the project root.
  2. Run maintain_french_titles.py and fill in French titles.
  3. Run this script.

Run from PyCharm.
"""

import csv
import json
import unicodedata

import config
import bgg_selenium
import scrape_metadata
import build_games  # reuse parsers


def build_collection():
    csv_path = config.PROJECT_ROOT / "collection.csv"
    if not csv_path.exists():
        raise RuntimeError(
            "collection.csv not found at the project root.")

    items = _load_owned_items(csv_path)
    print("Loaded {} owned items from collection.csv".format(len(items)))
    n_standalones = sum(1 for x in items if x["itemtype"] == "standalone")
    n_expansions  = sum(1 for x in items if x["itemtype"] == "expansion")
    print("  standalones: {}".format(n_standalones))
    print("  expansions : {}".format(n_expansions))

    _ensure_cache(items)
    french_titles = _load_french_titles()

    print()
    print("Loading metadata from cache...")
    for it in items:
        raw_path = config.CACHE_METADATA_DIR / "{}.json".format(it["bgg_id"])
        if not raw_path.exists():
            print("  WARN: no cache for bgg_id {} ({}), skipping".format(
                it["bgg_id"], it["english_title"]))
            it["raw"] = None
            continue
        with open(raw_path, encoding="utf-8") as f:
            it["raw"] = json.load(f)
    items = [it for it in items if it["raw"] is not None]

    # Build a reverse index: for each owned standalone, which owned expansions
    # list it in their `expands_boardgames`? Each expansion can attach to
    # multiple standalones (reboots, e.g. Dixit + Dixit: Odyssey).
    owned_ids = {it["bgg_id"] for it in items if it["itemtype"] == "standalone"}
    attached_per_std = {sid: [] for sid in owned_ids}  # std_id -> [expansion items]
    for it in items:
        if it["itemtype"] != "expansion":
            continue
        targets = (it["raw"].get("expands_boardgames") or [])
        for t in targets:
            tid = t.get("bgg_id")
            if tid in owned_ids:
                attached_per_std[tid].append(it)

    items_by_id = {it["bgg_id"]: it for it in items}
    standalones_out = []
    for it in items:
        if it["itemtype"] != "standalone":
            continue
        standalones_out.append(_build_standalone_entry(
            it, items_by_id, attached_per_std.get(it["bgg_id"], []),
            french_titles))

    # Default sort: my_rating desc, then title asc.
    standalones_out.sort(
        key=lambda e: (
            -(e.get("my_rating") if e.get("my_rating") is not None else -1),
            (e.get("title") or "").lower(),
        ))

    out_dir = config.PROJECT_ROOT / "docs" / "collection"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "collection_data.json"
    payload = {"games": standalones_out}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print()
    print("Wrote {} ({} standalones).".format(out_path, len(standalones_out)))

    # Sanity: any owned expansion not attached to any standalone we own?
    attached_exp_ids = set()
    for entry in standalones_out:
        for exp in entry.get("expansions", []):
            attached_exp_ids.add(exp["bgg_id"])
    orphan_expansions = [
        it for it in items
        if it["itemtype"] == "expansion" and it["bgg_id"] not in attached_exp_ids
    ]
    if orphan_expansions:
        print()
        print("Note: {} owned expansion(s) couldn't be attached to any "
              "owned standalone (their `expands_boardgames` mentions none of "
              "the games you own):".format(len(orphan_expansions)))
        for it in orphan_expansions:
            targets = (it["raw"].get("expands_boardgames") or [])
            target_str = ", ".join(t.get("name") or "?" for t in targets) or "(none)"
            print("  bgg_id={} '{}' → expands: {}".format(
                it["bgg_id"], it["english_title"], target_str))


def _load_owned_items(csv_path):
    items = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("own") != "1":
                continue
            rating = row.get("rating", "")
            try:
                rating = float(rating) if rating not in ("", None) else None
            except ValueError:
                rating = None
            items.append({
                "bgg_id": int(row["objectid"]),
                "english_title": row.get("objectname", ""),
                "rating": rating,
                "itemtype": row.get("itemtype", ""),
            })
    return items


def _ensure_cache(items):
    missing = []
    for it in items:
        cache_path = config.CACHE_METADATA_DIR / "{}.json".format(it["bgg_id"])
        if not cache_path.exists():
            missing.append(it)
    if not missing:
        print("All items already cached.")
        return
    print()
    print("{} items missing from cache. Scraping...".format(len(missing)))
    driver = bgg_selenium.make_driver(config.SELENIUM_HEADLESS)
    try:
        bgg_selenium.login(driver, config.BGG_USERNAME, config.BGG_PASSWORD)
        for i, it in enumerate(missing, 1):
            print("  [{}/{}] bgg_id={} ({}: {})".format(
                i, len(missing), it["bgg_id"],
                it["itemtype"], it["english_title"]))
            try:
                data = scrape_metadata.scrape_game(driver, it["bgg_id"])
                if data is not None:
                    scrape_metadata.save_metadata_cache(it["bgg_id"], data)
                else:
                    print("    failed: scrape_game returned None")
            except Exception as exc:
                print("    failed: {}".format(exc))
    finally:
        driver.quit()


def _load_french_titles():
    path = config.PROJECT_ROOT / "french_titles.json"
    if not path.exists():
        print("Note: french_titles.json not found; using English titles for all.")
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    titles = {}
    for k, v in data.items():
        if k == "_comment":
            continue
        if isinstance(v, dict):
            fr = v.get("french")
            if fr:
                titles[int(k)] = fr
        elif isinstance(v, str) and v:
            titles[int(k)] = v
    return titles


def _resolve_title(bgg_id, raw, french_titles):
    if bgg_id in french_titles:
        return french_titles[bgg_id]
    return (raw.get("credits_table") or {}).get("primary_name") or "?"


def _build_standalone_entry(it, items_by_id, attached_expansions, french_titles):
    raw = it["raw"]
    bgg_id = it["bgg_id"]
    title = _resolve_title(bgg_id, raw, french_titles)
    eng_title = (raw.get("credits_table") or {}).get("primary_name") or it["english_title"]

    players  = build_games.parse_players(raw)
    playtime = build_games.parse_playing_time(raw)
    age      = build_games.parse_age(raw)
    weight   = build_games.parse_weight(raw)
    year     = build_games.parse_year(raw)

    ct = raw.get("credits_table") or {}
    designers       = build_games.collect_links(ct, "boardgamedesigner")
    solo_designers  = build_games.collect_links(ct, "boardgamesolodesigner")
    artists         = build_games.collect_links(ct, "boardgameartist")
    publishers      = build_games.collect_links(ct, "boardgamepublisher")
    mechanics       = build_games.collect_links(ct, "boardgamemechanic")
    categories      = build_games.collect_links(ct, "boardgamecategory")
    families        = build_games.collect_links(ct, "boardgamefamily")

    # Owned expansions that BGG says expand THIS standalone, sorted by title.
    expansion_items = sorted(
        attached_expansions,
        key=lambda m: _resolve_title(
            m["bgg_id"], m["raw"], french_titles).lower())
    expansions_out = [
        {
            "bgg_id": m["bgg_id"],
            "title":  _resolve_title(m["bgg_id"], m["raw"], french_titles),
            "bgg_url": "https://boardgamegeek.com/boardgame/{}".format(m["bgg_id"]),
        }
        for m in expansion_items
    ]

    # search_blob: title + english + people + classifications + expansion titles,
    # all normalized (lowercase, no accents) for substring matching.
    blob_parts = [title, eng_title]
    for lst in (designers, solo_designers, artists, publishers,
                mechanics, categories, families):
        blob_parts.extend(p.get("name") or "" for p in lst)
    for exp in expansions_out:
        blob_parts.append(exp["title"])
    search_blob = _normalize(" ".join(blob_parts))

    search_index = {
        "publishers": publishers,
        "mechanics":  mechanics,
        "categories": categories,
        "families":   families,
    }

    return {
        "bgg_id":         bgg_id,
        "title":          title,
        "english_title":  eng_title if eng_title != title else None,
        "year":           year,
        "image_url":      raw.get("image_url"),
        "bgg_url":        "https://boardgamegeek.com/boardgame/{}".format(bgg_id),
        "players":        players,
        "playing_time":   playtime,
        "age":            age,
        "weight":         weight,
        "my_rating":      it["rating"],
        "designers":      designers,
        "solo_designers": solo_designers,
        "artists":        artists,
        "expansions":     expansions_out,
        "search_blob":    search_blob,
        "search_index":   search_index,
    }


def _normalize(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


if __name__ == "__main__":
    build_collection()