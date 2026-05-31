"""Post-process the raw metadata cache into a clean games.json.

Reads cache/game_metadata/<bgg_id>.json (the raw, faithfully-captured data
from scrape_metadata.py) and produces games.json, one entry per game in the
current edition's rankings cache.

Each output entry is the "ready-to-consume" shape used by the web page:
  {
    bgg_id, title, image_url, year,
    players: {
      official:  {min, max} | null,
      community: {min, max, values} | null,
      best:      {min, max, values} | null,
    },
    playing_time:  {min, max} | null,
    age:           {official, community} | null per sub-field,
    weight:        float | null,
    designers / artists / publishers / mechanics / categories / families:
      lists of {name, id} (deduplicated by id),
    solo_designers: list of {name, id},
  }

Design principle: this script is pure post-processing. It does NOT scrape.
Everything it consumes is in cache/game_metadata/. To iterate on parsing,
just edit and re-run; no network calls.

Parameters come from config.py (paths, START/END for the edition window).
Run from PyCharm.
"""

import json
import re

import config


# --- Helpers: parse ranges of integers ------------------------------------

def parse_int_range(s, with_values=False):
    """Parse a range string into {min, max[, values]}. Returns None on failure.

    Handles '30', '30 Min', '1-5', '3–4' (en-dash), '1, 3-5' (comma list).
    Also handles the BGG '+' suffix that appears in community polls when the
    poll's last option was 'more than N': '3-5+' becomes effectively '3-6',
    because the player count exceeds the official maximum (which is what
    BGG's poll mechanism encodes with that last "+" option).
    """
    if s is None:
        return None
    norm = s.replace("\u2013", "-").replace("\u2014", "-")
    # Expand "N+" → "N N+1" (handled before number extraction so both ends
    # of a "3-5+" or "5+" are captured).
    norm = re.sub(r"(\d+)\+", lambda m: "{} {}".format(m.group(1), int(m.group(1)) + 1), norm)
    nums = [int(n) for n in re.findall(r"\d+", norm)]
    if not nums:
        return None
    result = {"min": min(nums), "max": max(nums)}
    if with_values:
        values = set()
        # find tokens like "a-b" and individual ints
        for part in re.split(r"[,\s]+", norm):
            if "-" in part:
                bits = part.split("-")
                try:
                    a, b = int(bits[0]), int(bits[-1])
                    if a <= b:
                        values.update(range(a, b + 1))
                except ValueError:
                    pass
            elif part.isdigit():
                values.add(int(part))
        result["values"] = sorted(values)
    return result


# --- Field-specific parsers ------------------------------------------------

def parse_players(raw):
    """Build the players block from raw fields.

    raw is the metadata dict for one game. Returns:
      {official, community, best} -- each may be None.

    The 'official' is parsed without 'values' (BGG min/max are bounds, not a
    full per-count vote map). The 'community' and 'best' are parsed WITH
    'values', expanding ranges like 1-5 into [1,2,3,4,5] so the web page can
    filter by exact player count.
    """
    official = None
    off_raw = raw.get("players_official") or {}
    min_raw = off_raw.get("min_raw")
    max_raw = off_raw.get("max_raw")
    if min_raw or max_raw:
        # Build a small string and reparse for consistency.
        if min_raw and max_raw and min_raw != max_raw:
            official = parse_int_range("{}-{}".format(min_raw, max_raw))
        else:
            official = parse_int_range(min_raw or max_raw)

    # Community and Best come from the secondary text:
    # "Community: 1-5 — Best: 3-4"   or "Community: 2 — Best: 2"
    # The "+" suffix may appear (e.g. "Community: 3-5+") when BGG's poll
    # had a "more than N" terminal option; parse_int_range expands it.
    secondary = raw.get("players_secondary_text") or ""
    community = None
    best = None
    # Community: between 'Community:' and 'Best:' (or end)
    m_comm = re.search(
        r"Community:\s*([\d\u2013\u2014\-,\s+]+?)\s*(?:[\u2014\-]\s*Best|$)",
        secondary)
    if m_comm:
        community = parse_int_range(m_comm.group(1), with_values=True)
    m_best = re.search(r"Best:\s*([\d\u2013\u2014\-,\s+]+)", secondary)
    if m_best:
        best = parse_int_range(m_best.group(1), with_values=True)

    return {"official": official, "community": community, "best": best}


def parse_playing_time(raw):
    """Parse '30 Min', '30–150 Min', etc. into {min, max}.

    We do not expand values (a 30-150 game does not mean every integer
    duration is a thing). Returns None if no integer found.
    """
    text = raw.get("playtime_primary_text")
    if not text:
        return None
    # Strip 'Min' (case-insensitive) for robustness.
    cleaned = re.sub(r"\bmin\b", "", text, flags=re.IGNORECASE)
    return parse_int_range(cleaned)


def parse_age(raw):
    """Return {official, community} ints. Either may be None.

    official: BGG's editor-set 'minimum age' (from itemprop). null when BGG
    shows "Not provided by publisher".
    community: the integer from the secondary text 'Community: N+' (we drop
    the '+').
    """
    out = {"official": None, "community": None}
    off = raw.get("age_official_raw")
    if off:
        m = re.search(r"\d+", off)
        if m:
            out["official"] = int(m.group(0))
    sec = raw.get("age_secondary_text") or ""
    m = re.search(r"Community:\s*(\d+)", sec)
    if m:
        out["community"] = int(m.group(1))
    return out


def parse_weight(raw):
    """Extract the float weight from 'Weight: X.YZ / 5 ...'. Returns None."""
    text = raw.get("weight_primary_text") or ""
    # First decimal number after 'Weight:'.
    m = re.search(r"Weight:\s*([\d.]+)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_year(raw):
    """Pull an integer year from the credits table, or None."""
    yr = (raw.get("credits_table") or {}).get("year_released")
    if not yr:
        return None
    m = re.search(r"\d{4}", yr)
    return int(m.group(0)) if m else None


# --- Credits regrouping ---------------------------------------------------

# Output field name -> link type to collect under it.
LINK_FIELDS = [
    ("designers",      "boardgamedesigner"),
    ("solo_designers", "boardgamesolodesigner"),
    ("artists",        "boardgameartist"),
    ("publishers",     "boardgamepublisher"),
    ("mechanics",      "boardgamemechanic"),
    ("categories",     "boardgamecategory"),
    ("families",       "boardgamefamily"),
]


def collect_links(credits_table, link_type):
    """Return de-duplicated [{name, id, type}, ...] for all links of `link_type`.

    Scans EVERY row of credits_table, because BGG's row keys vary (designer
    vs designers, artist vs artists, etc.). We identify by the 'type' field
    on each link, which is stable. We keep the type in the output too because
    it doubles as the slug for the BGG URL (boardgamepublisher/.., etc.) the
    web UI builds for the "Match" disclosure.
    """
    seen = set()
    out = []
    if not isinstance(credits_table, dict):
        return out
    for value in credits_table.values():
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            if item.get("type") != link_type:
                continue
            person_id = item.get("id")
            name = item.get("name")
            if not name or person_id in seen:
                continue
            seen.add(person_id)
            out.append({
                "name": name,
                "id": person_id,
                "type": link_type,
            })
    return out


# --- Per-game build --------------------------------------------------------

def build_game_entry(raw):
    """Turn one raw metadata dict into the clean output shape."""
    ct = raw.get("credits_table") or {}
    title = ct.get("primary_name") or ""

    entry = {
        "bgg_id": raw.get("bgg_id"),
        "title": title,
        "image_url": raw.get("image_url"),
        "year": parse_year(raw),
        "players": parse_players(raw),
        "playing_time": parse_playing_time(raw),
        "age": parse_age(raw),
        "weight": parse_weight(raw),
    }
    for field, link_type in LINK_FIELDS:
        entry[field] = collect_links(ct, link_type)
    return entry


# --- Game-set discovery ----------------------------------------------------

def collect_ranked_ids():
    """Return the set of bgg_ids that appear in the rankings cache window.

    Reads cache/monthly_rankings/*.json restricted to [START, END).
    """
    from scrape_rankings import month_year_iter, month_cache_path
    ids = set()
    for (y, m) in month_year_iter(
            config.START_YEAR, config.START_MONTH,
            config.END_YEAR, config.END_MONTH):
        path = month_cache_path(y, m)
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        for g in payload.get("games", []):
            ids.add(g["bgg_id"])
    return ids


# --- Orchestration ---------------------------------------------------------

def build_games():
    ranked_ids = collect_ranked_ids()
    print("Distinct games in ranking window: {}".format(len(ranked_ids)))

    out = []
    missing_meta = []
    for bgg_id in sorted(ranked_ids):
        meta_path = config.CACHE_METADATA_DIR / "{}.json".format(bgg_id)
        if not meta_path.exists():
            missing_meta.append(bgg_id)
            continue
        with open(meta_path, encoding="utf-8") as f:
            raw = json.load(f)
        out.append(build_game_entry(raw))

    if missing_meta:
        print("WARNING: {} game(s) have no metadata file: {}".format(
            len(missing_meta), missing_meta[:10]))

    out_path = config.PROJECT_ROOT / "games.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"games": out}, f, ensure_ascii=False, indent=2)
    print("Wrote {} ({} games).".format(out_path, len(out)))


if __name__ == "__main__":
    build_games()